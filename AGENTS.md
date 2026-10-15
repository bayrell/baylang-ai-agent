# AGENTS.md

Инструкция для AI-агентов, работающих с этим репозиторием.

## Обзор

**BayLang AI** — система foreground-выполнения задач. Сервер (PHP + SQLite) раздаёт
задачи агентам; клиент (Python) опрашивает сервер раз в `POLL_INTERVAL` секунд (по
умолчанию 300) и выполняет задачи через AI (pydantic-ai + OpenRouter): `git pull` → копирует задачу в `docs/task.md` →
AI выполняет → коммит → `push` → отчёт на сервер.

## Структура проекта

- `server/` — сервер задач (PHP, без фреймворков): `api.php` (REST API), `index.php`
  (интерфейс), `config.php` (basic auth + путь к SQLite), `main.css`, `main.js`
- `src/` — AI-клиент (Python): `main.py` (точка входа), `app.py` (агент и AI-обёртка),
  `foreground.py` (цикл опроса сервера), `run.sh` (настройка git из env и запуск `main.py`)
- `Dockerfile` — контейнер клиента (foreground)
- `build.sh` — сборка docker-образа (`./build.sh docker`)
- `requirements.txt` — зависимости Python

## Запуск

Сервер (для разработки):

```bash
php -S 0.0.0.0:8080 -t server
```

Клиент (из папки `src/`, конфиг в `~/.baylang/config.json`):

```bash
./src/main.py --foreground   # цикл foreground (опрос сервера каждые 5 минут)
./src/main.py                # интерактивный режим
```

Docker (образ `bayrell/baylang-ai-agent:1.0.0`):

```bash
./build.sh docker
docker run -d \
    --env OPENROUTER_API_KEY="" \
    --env OPENROUTER_MODEL="openrouter/auto" \
    --env TZ="Asia/Almaty" \
    --env GIT_USER_NAME="BayLang Agent" \
    --env GIT_USER_EMAIL="agent@baylang.local" \
    --name baylang_agent \
    -v ./baylang:/data/home \
    -v ./project:/data/home/project \
    bayrell/baylang-ai-agent:1.0.0
```

## Переменные окружения

- `OPENROUTER_API_KEY` — API-ключ OpenRouter (обязательна)
- `OPENROUTER_MODEL` — модель, например `openrouter/auto` (обязательна)
- `OPENROUTER_PROVIDERS` — (необяз.) список разрешённых провайдеров через запятую
- `TZ` — часовой пояс, например `Asia/Almaty`
- `GIT_USER_NAME` — (необяз.) `git config --global user.name` для коммитов
- `GIT_USER_EMAIL` — (необяз.) `git config --global user.email` для коммитов
- `BAYLANG_SERVER` — (необяз.) URL сервера задач, перекрывает `server` в config.json
- `BAYLANG_LOGIN` — (необяз.) логин basic auth, перекрывает `login` в config.json
- `BAYLANG_PASSWORD` — (необяз.) пароль basic auth, перекрывает `password` в config.json
- `BAYLANG_AGENT` — (необяз.) api name агента, перекрывает `agent` в config.json
- `BAYLANG_PROJECTS` — (необяз.) проекты в формате JSON `{"api_name": "/path"}` или
  `api_name=/path, ...`, перекрывает `projects` в config.json
- `POLL_INTERVAL` — (необяз.) интервал опроса сервера в секундах, по умолчанию `300`

Переменные `BAYLANG_*`, если установлены, перекрывают config.json: обновлённый конфиг
сохраняется обратно в `~/.baylang/config.json` (см. `apply_env_config` в `src/foreground.py`).

Переменные можно задать через `--env`, `--env-file .env` или файл `.env` в рабочей
папке (читается автоматически через `python-dotenv` в `src/main.py`).

## Конфигурация клиента

Файл `~/.baylang/config.json`:

```json
{
  "server": "http://localhost:8080",
  "login": "admin",
  "password": "admin",
  "agent": "agent-1",
  "projects": {
    "baylang": "/data/home/project"
  }
}
```

- `agent` — api name агента на сервере
- `projects` — соответствие api name проекта и локального пути

## Workflow задачи (foreground, `src/foreground.py`)

1. Каждые `POLL_INTERVAL` секунд (env, по умолчанию 300) запрашивает у сервера задачи со статусом `planned`
2. `task_start` → `git pull` → `git checkout <ветка>` (ветка из задачи, иначе ветка
   по умолчанию проекта `projects.branch`, иначе `main`)
3. Содержимое задачи (`task.content`) записывается в `docs/task.md` проекта
4. AI выполняет задание из `docs/task.md`
5. `git add -A` → коммит (дата берётся из `get_commit_date`, если команда в PATH; если дата
   коммита в будущем — ожидание её наступления перед push) → `push`
6. Отчёт на сервер: `task_done` либо `task_error`

## Конвенции

- **Python 3.12**, pydantic-ai + pydantic-ai-harness; типы через pydantic
- **PHP** — без фреймворков, basic auth через `check_auth()` в `server/config.php`
- Даты в базе хранятся в **UTC**, формат `y-m-d h:i:s`
- Интерфейс сервера — AJAX без перезагрузки, адаптирован под мобильные
- Логи клиента: `~/.baylang/logs/foreground.log` с ротацией, дублируются в stdout (docker)

## Важные файлы

- `docs/task.md` — текущее задание (создаётся автоматически из задачи на сервере)
- `server/data.sqlite` — база данных (в `.gitignore`, не коммитить)
- `~/.baylang/config.json` — конфиг клиента (создаётся автоматически с дефолтом)
