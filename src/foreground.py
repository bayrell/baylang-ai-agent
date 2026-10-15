"""Foreground-система: опрашивает сервер и выполняет задачи агента."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx

from app import AI, build_software_engineer

logger = logging.getLogger(__name__)

BAYLANG_DIR = Path.home() / ".baylang"
CONFIG_FILE = BAYLANG_DIR / "config.json"
LOG_DIR = BAYLANG_DIR / "logs"

POLL_INTERVAL = 300  # 5 минут


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


def apply_env_config(config: dict) -> bool:
    """Перекрывает config.json переменными окружения BAYLANG_*.

    Если переменная установлена и не пустая — её значение имеет приоритет
    над config.json. Возвращает True, если конфиг изменился.
    """
    changed = False
    for key, env_name in (
        ("server", "BAYLANG_SERVER"),
        ("login", "BAYLANG_LOGIN"),
        ("password", "BAYLANG_PASSWORD"),
        ("agent", "BAYLANG_AGENT"),
    ):
        value = os.getenv(env_name)
        if value:
            config[key] = value
            changed = True

    projects = os.getenv("BAYLANG_PROJECTS")
    if projects:
        config["projects"] = parse_projects(projects)
        changed = True

    return changed


def load_config() -> dict:
    """Читает ~/.baylang/config.json: сервер, авторизация, агент, проекты.

    Если файла нет — создаёт его с конфигом по умолчанию.
    Если установлены переменные окружения BAYLANG_* — они перекрывают
    config.json, и обновлённый конфиг сохраняется обратно в файл.
    """
    if not CONFIG_FILE.exists():
        config = DEFAULT_CONFIG.copy()
        save_config(config)
        logger.info("Создан конфиг по умолчанию: %s", CONFIG_FILE)
    else:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

    if apply_env_config(config):
        save_config(config)
        logger.info("Конфиг обновлён из переменных окружения: %s", CONFIG_FILE)

    return config


class GitError(RuntimeError):
    pass


def run_git(path: str, *args, env=None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        env=env,
    )
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


async def process_task(task: dict, config: dict, agent_name: str):
    """Полный цикл задачи: git pull -> ветка -> task.md -> AI -> commit -> push."""
    project_api = task["project_api_name"]
    project_path = config.get("projects", {}).get(project_api)
    if not project_path:
        raise RuntimeError(f"Проект '{project_api}' не найден в config.json")

    task_id = task["id"]
    branch = task.get("branch") or "main"
    logger.info(
        "Задача %s (проект %s, ветка %s)",
        task["name"], project_api, branch,
    )

    # Скачиваем проект и переключаемся на ветку
    try:
        run_git(project_path, "pull")
    except GitError as e:
        logger.warning("git pull не удался: %s", e)
    try:
        run_git(project_path, "checkout", branch)
    except GitError:
        run_git(project_path, "checkout", "-B", branch)

    # Записываем задание в docs/task.md (содержимое задачи из task.content)
    docs_dir = Path(project_path) / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    content = (task.get("content") or "").strip()
    text = content if content else f"Задача: {task['name']}\n"
    (docs_dir / "task.md").write_text(text, encoding="utf-8")

    # Создаём AI с указанием path и выполняем задание
    ai = AI(build_software_engineer(path=project_path))
    answer = await ai.send("Изучи проект и выполни задание из docs/task.md")

    # Коммит (с датой из get_commit_date, если есть в PATH) и push
    run_git(project_path, "add", "-A")
    env = os.environ.copy()
    prev_ts = run_git(project_path, "log", "-1", "--format=%ct") or "0"
    commit_date = get_commit_date(int(prev_ts))
    if commit_date:
        env["GIT_AUTHOR_DATE"] = commit_date
        env["GIT_COMMITTER_DATE"] = commit_date
    run_git(project_path, "commit", "-m", f"{task['name']}", env=env)
    run_git(project_path, "push")
    logger.info("Задача %s закоммичена и запушена", task['name'])


async def run_foreground():
    """Главный цикл foreground: раз в 5 минут запрашивает план с сервера."""
    setup_logging()
    config = load_config()
    server = ServerClient(
        config["server"],
        config.get("login", DEFAULT_CONFIG["login"]),
        config.get("password", DEFAULT_CONFIG["password"]),
    )
    agent_name = config["agent"]
    logger.info("Foreground запущен. Агент: %s, сервер: %s", agent_name, config["server"])

    while True:
        try:
            tasks = []
            try:
                tasks = await server.planned_tasks(agent_name)
                logger.info("Получено задач с сервера: %d", len(tasks))
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

        await asyncio.sleep(POLL_INTERVAL)
