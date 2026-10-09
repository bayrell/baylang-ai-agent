import os
import json
import time
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
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
from pydantic_ai.capabilities import LocalWorkspace, Hooks
from pydantic_ai_harness import FileSystem, RepoContext, ClearToolResults


APP_URL = "https://baylang.com/"
APP_TITLE = "BayLang AI"

BAYLANG_DIR = Path.home() / ".baylang"
HISTORY_DIR = BAYLANG_DIR / "history"
PROMPT_FILE = BAYLANG_DIR / "prompt.txt"

load_dotenv(dotenv_path=find_dotenv(usecwd=True))

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
    )

    return agent


def build_software_engineer(capabilities=None):
    if capabilities is None:
        capabilities = []

    capabilities.extend([
        LocalWorkspace(working_dir=os.getcwd()),
        FileSystem(),
        RepoContext(),
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

        # системный промпт из ~/.baylang/prompt.txt
        prompt = load_prompt()
        if prompt:
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
        self.context.append(
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
