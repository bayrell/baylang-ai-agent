import os
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic_core import to_jsonable_python
from pydantic_ai import (
    Agent,
    RunContext,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    UserPromptPart,
    TextPart,
    FunctionToolCallEvent,
)
from pydantic_ai.models.openrouter import (
    OpenRouterModel,
    OpenRouterModelSettings,
    OpenRouterProviderConfig,
)
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.capabilities import AbstractCapability, LocalWorkspace, Hooks
from pydantic_ai.toolsets import AgentToolset, FunctionToolset
from pydantic_ai_harness import FileSystem, RepoContext, ClearToolResults


APP_URL = "https://baylang.com/"
APP_TITLE = "BayLang AI"

BAYLANG_DIR = Path.home() / ".baylang"
HISTORY_DIR = BAYLANG_DIR / "history"
PROMPT_FILE = BAYLANG_DIR / "prompt.txt"

hooks = Hooks()


@hooks.on.event(FunctionToolCallEvent)
async def event_tool(ctx: RunContext, event: FunctionToolCallEvent) -> None:
    print(f"Tool: {event.part.tool_name}")


def build_agent(capabilities=None):
    if capabilities is None:
        capabilities = []

    config = OpenRouterProviderConfig()

    if os.getenv("OPENROUTER_PROVIDERS"):
        items = os.getenv("OPENROUTER_PROVIDERS").split(",")
        config["only"] = list(map(lambda s: s.strip(), items))

    model = OpenRouterModel(
        os.getenv("OPENROUTER_MODEL"),
        provider=OpenRouterProvider(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            app_url=APP_URL,
            app_title=APP_TITLE,
        ),
        settings=OpenRouterModelSettings(
            openrouter_cache_instructions=True,
            openrouter_cache_messages=True,
            openrouter_cache_tool_definitions=True,
            openrouter_provider=config,
        ),
    )

    capabilities.append(hooks)

    agent = Agent(
        model,
        capabilities=capabilities,
        retries=10
    )

    return agent


GIT_DIFF_MAX_CHARS = 50_000


def detect_base_branch(path: str) -> str | None:
    """Ищет базовую ветку для сравнения: main, master, origin/main, origin/master."""
    for ref in ("main", "master", "origin/main", "origin/master"):
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", ref],
                cwd=path,
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode == 0:
            return ref
    return None


def build_git_diff_toolset(path: str) -> FunctionToolset:
    """Toolset с инструментом git diff: изменения ветки относительно main/master."""
    toolset = FunctionToolset()

    @toolset.tool_plain
    def git_diff(base: str = "") -> str:
        """git diff текущей ветки относительно main (или master).

        Показывает список изменений (файлы и строки) текущей фичи
        по отношению к базовой ветке — полезно для code review.
        base — базовая ветка для сравнения (по умолчанию main или master).
        """
        base = base.strip() or detect_base_branch(path)
        if not base:
            return "Базовая ветка (main/master) не найдена — сравнение невозможно"

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            result = subprocess.run(
                ["git", "diff", base],
                cwd=path,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return f"git diff {base}: превышено время ожидания"
        if result.returncode != 0:
            return f"git diff {base}: {result.stderr.strip()}"

        out = result.stdout.strip()

        # Новые (untracked) файлы git diff не показывает — добавляем их списком
        try:
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            untracked = None
        if untracked is not None and untracked.returncode == 0 and untracked.stdout.strip():
            files = untracked.stdout.strip()
            section = f"### Новые файлы (untracked):\n{files}"
            out = f"{out}\n\n{section}" if out else section

        if not out:
            return f"Изменений относительно {base} нет"
        if len(out) > GIT_DIFF_MAX_CHARS:
            out = out[:GIT_DIFF_MAX_CHARS] + f"\n... (обрезано, всего символов: {len(out)})"
        return out

    return toolset


@dataclass
class GitDiffTools(AbstractCapability[Any]):
    """Инструмент git diff: изменения текущей ветки относительно main/master."""

    path: str = ""

    def get_toolset(self) -> AgentToolset[Any] | None:
        return build_git_diff_toolset(self.path or os.getcwd())


def build_software_engineer(path=None, capabilities=None):
    if capabilities is None:
        capabilities = []
    
    if path is None:
        path = os.getcwd()
    
    capabilities.extend([
        LocalWorkspace(working_dir=path),
        FileSystem(),
        RepoContext(),
        GitDiffTools(path=path),
        ClearToolResults(
            keep_pairs=6,
            max_fraction=0.6,
            min_clear_tokens=20_000,
        ),
    ])

    return build_agent(capabilities)


def load_prompt() -> str:
    """Читает системный промпт из ~/.baylang/prompt.txt"""
    try:
        return PROMPT_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


class AI:
    def __init__(self, agent):
        self.agent = agent
        self.history = []      # лёгкая история: только user/assistant
        self.context = []      # полный message_history для agent.run
        self.id = str(int(time.time()))
        self.file_name = str(HISTORY_DIR / f"{self.id}.json")

        # системный промпт из ~/.baylang/prompt.txt + текущая дата и время
        prompt = load_prompt()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = f"{prompt}\n\nТекущая дата и время: {now}".strip()
        self.add_prompt(prompt)

    # --- persistence -------------------------------------------------

    def save(self):
        """Сохраняет историю в ~/.baylang/history/<unixtimestamp>.json"""
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "id": self.id,
            "history": to_jsonable_python(self.history),
            "context": to_jsonable_python(self.context),
        }
        with open(self.file_name, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path=None):
        """Восстанавливает историю из json-файла."""
        path = path or self.file_name
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return False

        self.id = data.get("id", self.id)
        self.history = data.get("history", [])
        self.context = []
        for msg in data.get("context", []):
            rebuilt = rebuild_message(msg)
            if rebuilt is not None:
                self.context.append(rebuilt)
        return True

    # --- conversation ------------------------------------------------

    def add_prompt(self, prompt):
        self.context.append(
            ModelRequest(parts=[SystemPromptPart(content=prompt)])
        )

    async def send(self, user_message: str) -> str:
        """Один шаг agent loop: user -> agent -> assistant."""
        self.history.append(
            ModelRequest(parts=[UserPromptPart(content=user_message)])
        )

        result = await self.agent.run(
            user_message,
            message_history=self.context,
        )

        self.history.append(
            ModelResponse(parts=[TextPart(content=result.output)])
        )
        # полная переписка (с ответами инструментов) уходит в контекст
        self.context = list(result.all_messages())
        return result.output


def rebuild_message(msg: dict):
    """Превращает json-словарь обратно в ModelRequest/ModelResponse."""
    parts = []
    for part in msg.get("parts", []):
        kind = part.get("part_kind") or part.get("type")
        try:
            if kind == "system-prompt":
                parts.append(SystemPromptPart(content=part["content"]))
            elif kind == "user-prompt":
                parts.append(UserPromptPart(content=part["content"]))
            elif kind == "text":
                parts.append(TextPart(content=part["content"]))
            else:
                # прочие части (tool calls и т.п.) пропускаем аккуратно
                continue
        except (KeyError, TypeError):
            continue

    if not parts:
        return None

    kind = msg.get("message_kind") or msg.get("kind")
    if kind == "response" or msg.get("role") == "assistant":
        return ModelResponse(parts=parts)
    return ModelRequest(parts=parts)


async def run_loop(ai: AI):
    """Agent Loop: читает ввод, отправляет агенту, печатает ответ, сохраняет историю."""
    print("BayLang AI готов. Команды: /exit — выход.")

    while True:
        try:
            user_message = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            break

        if not user_message:
            continue

        if user_message in ("/exit", "/quit", "/q"):
            ai.save()
            print("История сохранена. Пока!")
            break

        try:
            answer = await ai.send(user_message)
        except Exception as e:
            print(f"Ошибка: {e}")
            continue

        print(answer)
        ai.save()

    return 0
