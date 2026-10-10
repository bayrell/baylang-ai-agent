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


def load_config() -> dict:
    """Читает ~/.baylang/config.json: сервер, авторизация, агент, проекты."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


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

    def __init__(self, url: str, password: str):
        self.url = url.rstrip("/") + "/api.php"
        self.client = httpx.AsyncClient(
            auth=httpx.BasicAuth("agent", password),
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

    # Копируем задачу в docs/task.md
    docs_dir = Path(project_path) / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "task.md").write_text(
        f"# Задача: {task['name']}\n\n",
        encoding="utf-8",
    )

    # Создаём AI с указанием path и выполняем задание
    ai = AI(build_software_engineer(path=project_path))
    answer = await ai.send("Изучи проект и выполни задание из файла docs/task.md")

    # Коммит (с датой из get_commit_date, если есть в PATH) и push
    run_git(project_path, "add", "-A")
    env = os.environ.copy()
    prev_ts = run_git(project_path, "log", "-1", "--format=%ct") or "0"
    commit_date = get_commit_date(int(prev_ts))
    if commit_date:
        env["GIT_AUTHOR_DATE"] = commit_date
        env["GIT_COMMITTER_DATE"] = commit_date
    run_git(project_path, "commit", "-m", f"Task {task['name']}", env=env)
    run_git(project_path, "push")
    logger.info("Задача %s закоммичена и запушена", task['name'])


async def run_foreground():
    """Главный цикл foreground: раз в 5 минут запрашивает план с сервера."""
    setup_logging()
    config = load_config()
    server = ServerClient(config["server"], config["password"])
    agent_name = config["agent"]
    logger.info("Foreground запущен. Агент: %s, сервер: %s", agent_name, config["server"])

    while True:
        try:
            tasks = await server.planned_tasks(agent_name)
            logger.info("Получено задач с сервера: %d", len(tasks))

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
        except Exception:
            logger.exception("Ошибка цикла foreground")

        await asyncio.sleep(POLL_INTERVAL)
