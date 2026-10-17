"""Foreground-система: опрашивает сервер и выполняет задачи агента."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx

from app import AI, build_software_engineer

logger = logging.getLogger(__name__)

BAYLANG_DIR = Path.home() / ".baylang"
CONFIG_FILE = BAYLANG_DIR / "config.json"
LOG_DIR = BAYLANG_DIR / "logs"

DEFAULT_POLL_INTERVAL = 300  # 5 минут


def get_poll_interval() -> int:
    """Интервал опроса сервера в секундах: env POLL_INTERVAL, иначе 300.

    Некорректное или неположительное значение заменяется дефолтом,
    чтобы цикл не завис в tight-loop при POLL_INTERVAL=0.
    """
    try:
        interval = int(os.getenv("POLL_INTERVAL", ""))
        if interval > 0:
            return interval
        logger.warning("POLL_INTERVAL=%d не положителен, используется %d", interval, DEFAULT_POLL_INTERVAL)
    except ValueError:
        if os.getenv("POLL_INTERVAL"):
            logger.warning("POLL_INTERVAL=%r не число, используется %d",
                           os.getenv("POLL_INTERVAL"), DEFAULT_POLL_INTERVAL)
    return DEFAULT_POLL_INTERVAL


def setup_logging():
    """Логи в ~/.baylang/logs с ротацией + вывод в stdout (docker)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        LOG_DIR / "foreground.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)


DEFAULT_CONFIG = {
    "server": "http://localhost:8080",
    "login": "admin",
    "password": "admin",
    "agent": "agent-1",
    "projects": {},
}


def save_config(config: dict):
    """Сохраняет ~/.baylang/config.json."""
    BAYLANG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def parse_projects(value: str) -> dict:
    """Парсит список проектов из env: JSON {"api_name": "/path"} или "api_name=/path, ...".

    Формат с '=' удобнее задавать в docker run, JSON — в .env-файлах.
    """
    value = value.strip()
    if value.startswith("{"):
        return json.loads(value)
    projects = {}
    for item in value.split(","):
        name, sep, path = item.partition("=")
        if sep:
            projects[name.strip()] = path.strip()
    return projects


def scan_projects_dir(path: str) -> dict:
    """Собирает проекты из папки: имя вложенной папки — это api name проекта.

    Путь задаётся env BAYLANG_PROJECTS_DIR; сканируются только обычные папки
    (скрытые вроде .git пропускаются).
    """
    projects = {}
    for entry in sorted(Path(path).iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            projects[entry.name] = str(entry)
    return projects


def reload_projects(config: dict) -> bool:
    """Перечитывает проекты из env: BAYLANG_PROJECTS либо BAYLANG_PROJECTS_DIR.

    BAYLANG_PROJECTS (явный словарь) имеет приоритет над BAYLANG_PROJECTS_DIR.
    Папка с проектами пересканируется — новые проекты могут появиться,
    пока демон работает. Возвращает True, если конфиг изменился.
    """
    projects = os.getenv("BAYLANG_PROJECTS")
    if projects:
        try:
            config["projects"] = parse_projects(projects)
            return True
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("BAYLANG_PROJECTS задан некорректно (%s) — используются проекты из config.json", e)
            return False

    projects_dir = os.getenv("BAYLANG_PROJECTS_DIR")
    if projects_dir:
        if Path(projects_dir).is_dir():
            config["projects"] = scan_projects_dir(projects_dir)
            return True

    return False


def apply_env_config(config: dict) -> bool:
    """Перекрывает config.json переменными окружения BAYLANG_*.

    Если переменная установлена и не пустая — её значение имеет приоритет
    над config.json.
    """
    for key, env_name in (
        ("server", "BAYLANG_SERVER"),
        ("login", "BAYLANG_LOGIN"),
        ("password", "BAYLANG_PASSWORD"),
        ("agent", "BAYLANG_AGENT"),
    ):
        value = os.getenv(env_name)
        if value:
            config[key] = value


def load_config() -> dict:
    """Читает ~/.baylang/config.json: сервер, авторизация, агент, проекты.

    Если файла нет — создаёт его с конфигом по умолчанию.
    """
    if not CONFIG_FILE.exists():
        config = DEFAULT_CONFIG.copy()
        save_config(config)
        logger.info("Создан конфиг по умолчанию: %s", CONFIG_FILE)
        return config

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        if not isinstance(config, dict):
            raise ValueError("ожидался JSON-объект")
        return config
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.error("Не удалось прочитать %s (%s) — используется конфиг по умолчанию",
                     CONFIG_FILE, e)
        return DEFAULT_CONFIG.copy()


class GitError(RuntimeError):
    pass


def run_git(path: str, *args, env=None) -> str:
    """Выполняет git-команду с таймаутом и без интерактивных промптов.

    GIT_TERMINAL_PROMPT=0 и GIT_SSH_COMMAND=BatchMode=yes не дают git
    зависнуть, запрашивая креды (HTTPS-пароль, SSH-фразу); timeout — при
    зависании сети.
    """
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env["GIT_TERMINAL_PROMPT"] = "0"
    run_env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=path,
            capture_output=True,
            text=True,
            env=run_env,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"git {' '.join(args)}: превышен таймаут 300 сек") from None
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def get_commit_date(prev_timestamp: int) -> str | None:
    """Если get_commit_date есть в PATH — запускает её, возвращает дату коммита."""
    exe = shutil.which("get_commit_date")
    if not exe:
        return None
    result = subprocess.run(
        [exe, str(prev_timestamp)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("get_commit_date завершился с ошибкой: %s", result.stderr.strip())
        return None
    return result.stdout.strip() or None


async def wait_commit_date(commit_date: str | None):
    """Ждёт до времени commit_date перед push (None/пусто — не ждёт)."""
    if not commit_date:
        return
    try:
        dt = int(commit_date)
    except (TypeError, ValueError):
        logger.warning("Некорректная дата коммита %r — ожидание пропущено", commit_date)
        return
    delay = dt - datetime.now().timestamp()
    if delay <= 0:
        return
    logger.info("Ожидание до времени коммита %s (%d сек)", commit_date, int(delay))
    await asyncio.sleep(delay)


class ServerClient:
    """Клиент API сервера задач."""

    def __init__(self, url: str, login: str, password: str):
        self.url = url.rstrip("/") + "/api.php"
        self.client = httpx.AsyncClient(
            auth=httpx.BasicAuth(login, password),
            timeout=30,
        )

    async def _get(self, action: str, **params):
        r = await self.client.get(self.url, params={"action": action, **params})
        r.raise_for_status()
        return r.json()

    async def _post(self, action: str, data: dict):
        r = await self.client.post(self.url, params={"action": action}, json=data)
        r.raise_for_status()
        return r.json()

    async def planned_tasks(self, agent: str):
        """Задачи со статусом 'planned' для данного агента."""
        return await self._get("plan", agent=agent)

    async def task_start(self, task_id: int, agent: str):
        return await self._post("task_start", {"id": task_id, "agent": agent})

    async def task_done(self, task_id: int, agent: str):
        return await self._post("task_done", {"id": task_id, "agent": agent})

    async def task_error(self, task_id: int, agent: str, error: str):
        return await self._post("task_error", {"id": task_id, "agent": agent, "error": error})

    async def close(self):
        """Закрывает HTTP-клиент при остановке демона."""
        await self.client.aclose()


async def process_task(task: dict, config: dict, agent_name: str):
    """Полный цикл задачи: git pull -> ветка -> task.md -> AI -> commit -> push."""
    project_api = task["project_api_name"]
    project_path = config.get("projects", {}).get(project_api)
    if not project_path:
        raise RuntimeError(f"Проект '{project_api}' не найден в config.json")

    task_id = task["id"]
    # Ветка задачи, иначе ветка по умолчанию из настроек проекта, иначе main
    branch = task.get("branch") or task.get("project_branch") or "main"
    logger.info(
        "Задача %s (проект %s, ветка %s)",
        task["name"], project_api, branch,
    )

    # Чистим дерево от предыдущей задачи (иначе её изменения вложатся в этот коммит)
    try:
        status = run_git(project_path, "status", "--porcelain")
    except GitError as e:
        raise RuntimeError(f"Не git-репозиторий или ошибка статуса: {e}") from e
    if status:
        run_git(project_path, "reset", "--hard")
        run_git(project_path, "clean", "-fd")

    # fetch -> checkout целевой ветки -> pull --ff-only уже на этой ветке
    try:
        run_git(project_path, "fetch", "origin")
    except GitError as e:
        logger.warning("git fetch не удался: %s", e)
    try:
        run_git(project_path, "checkout", branch)
    except GitError:
        run_git(project_path, "checkout", "-B", branch)
    try:
        run_git(project_path, "pull", "--ff-only")
    except GitError as e:
        logger.warning("git pull --ff-only не удался: %s", e)

    # Записываем задание в docs/task.md (содержимое задачи из task.content)
    docs_dir = Path(project_path) / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    content = (task.get("content") or "").strip()
    text = content if content else f"Задача: {task['name']}\n"
    (docs_dir / "task.md").write_text(text, encoding="utf-8")

    # Создаём AI с указанием path и выполняем задание
    ai = AI(build_software_engineer(path=project_path))
    answer = await ai.send("Изучи проект и выполни задание из docs/task.md")
    
    # Save history
    ai.save()

    # Коммит (с датой из get_commit_date, если есть в PATH) и push
    run_git(project_path, "add", "-A")
    env = os.environ.copy()
    prev_ts = run_git(project_path, "log", "-1", "--format=%ct") or "0"
    commit_date = get_commit_date(int(prev_ts))
    if commit_date:
        env["GIT_AUTHOR_DATE"] = commit_date
        env["GIT_COMMITTER_DATE"] = commit_date
    run_git(project_path, "commit", "-m", f"{task['name']}", env=env)
    # Если дата коммита в будущем — ждём её наступления перед push
    if commit_date:
        await wait_commit_date(commit_date)
    # push -u: новая ветка (созданная checkout -B) иначе падает с «no upstream branch»
    run_git(project_path, "push", "-u", "origin", branch)
    logger.info("Задача %s закоммичена и запушена", task['name'])


async def run_foreground():
    """Главный цикл foreground: раз в POLL_INTERVAL секунд запрашивает план с сервера."""
    setup_logging()
    config = load_config()
    apply_env_config(config)
    server_url = config.get("server") or DEFAULT_CONFIG["server"]
    server = ServerClient(
        server_url,
        config.get("login", DEFAULT_CONFIG["login"]),
        config.get("password", DEFAULT_CONFIG["password"]),
    )
    agent_name = config.get("agent") or DEFAULT_CONFIG["agent"]
    poll_interval = get_poll_interval()

    try:
        while True:
            try:
                tasks = []
                try:
                    tasks = await server.planned_tasks(agent_name)
                    logger.info("Получено задач с сервера: %d", len(tasks))
                except httpx.HTTPStatusError as e:
                    logger.error("Сервер ответил %s: %s", e.response.status_code, e)
                except httpx.ConnectError as e:
                    logger.exception("Сервер недоступен: %s", e)
                except httpx.TimeoutException:
                    logger.warning("Таймаут подключения к серверу")

                # Берём только одну задачу за цикл: после обработки выходим из перебора
                for task in tasks:
                    started = await server.task_start(task["id"], agent_name)
                    if not started.get("ok"):
                        logger.info("Задача %s уже взята другим воркером", task["name"])
                        continue
                    try:
                        # Перечитываем проекты: в BAYLANG_PROJECTS_DIR могли появиться новые папки
                        reload_projects(config)
                        await process_task(task, config, agent_name)
                        await server.task_done(task["id"], agent_name)
                        logger.info("Задача %s выполнена", task["name"])
                    except Exception as e:
                        logger.exception("Ошибка при выполнении задачи %s", task["name"])
                        try:
                            await server.task_error(task["id"], agent_name, str(e))
                        except Exception:
                            logger.exception("Не удалось отправить ошибку на сервер")
                    break
            except Exception:
                logger.exception("Ошибка цикла foreground")

            break
    finally:
        try:
            await server.close()
        except Exception:
            logger.exception("Не удалось закрыть HTTP-клиент")
