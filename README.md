# BayLang AI

Система foreground-выполнения задач: сервер (PHP + SQLite) раздаёт задачи агентам,
клиент (Python) опрашивает сервер раз в `POLL_INTERVAL` секунд (по умолчанию 300) и
выполняет задачи через AI.

## Структура

- `server/` — сервер задач (PHP): `api.php`, `index.php`, `config.php`, `main.css`, `main.js`
- `src/` — AI-клиент: `main.py`, `app.py`, `foreground.py`, `run.sh`
- `Dockerfile` — контейнер клиента (foreground)

## Сервер

Конфигурация в `server/config.php` (пароль для basic auth, путь к SQLite).
База данных создаётся автоматически. Даты хранятся в UTC формате `y-m-d h:i:s`.

Запуск (для разработки):

```bash
php -S 0.0.0.0:8080 -t server
```

Интерфейс: `http://localhost:8080/` (basic auth, пароль из config.php).
Список задач с фильтрами (статус, агент, проект, название), пагинация,
CRUD задач/проектов/агентов — всё через AJAX без перезагрузки, адаптировано под мобильные.

## Клиент

Конфигурация в `~/.baylang/config.json`:

```json
{
  "server": "http://localhost:8080",
  "login": "admin",
  "password": "admin",
  "agent": "agent-1",
  "projects": {
    "baylang": "/data/projects/baylang"
  }
}
```

- `agent` — api name агента на сервере
- `projects` — соответствие api name проекта и локального пути

### Переменные окружения

| Переменная | Обязательна | Описание |
|---|---|---|
| `OPENROUTER_API_KEY` | да | API-ключ [OpenRouter](https://openrouter.ai/) для доступа к моделям |
| `OPENROUTER_MODEL` | да | Используемая модель, например `openrouter/auto` |
| `OPENROUTER_PROVIDERS` | нет | Список разрешённых провайдеров через запятую |
| `TZ` | нет | Часовой пояс, например `Asia/Almaty` |
| `GIT_USER_NAME` | нет | `git config --global user.name` для коммитов агента |
| `GIT_USER_EMAIL` | нет | `git config --global user.email` для коммитов агента |
| `BAYLANG_SERVER` | нет | URL сервера задач, например `http://localhost:8080` |
| `BAYLANG_LOGIN` | нет | Логин basic auth на сервере задач |
| `BAYLANG_PASSWORD` | нет | Пароль basic auth на сервере задач |
| `BAYLANG_AGENT` | нет | Api name агента на сервере задач |
| `BAYLANG_PROJECTS` | нет | Проекты: JSON `{"api_name": "/path"}` или `api_name=/path, ...` |
| `POLL_INTERVAL` | нет | Интервал опроса сервера в секундах, по умолчанию `300` |

Переменные `BAYLANG_*` **перекрывают** значения из `config.json`: если они установлены,
обновлённый конфиг сохраняется обратно в `~/.baylang/config.json`.

Переменные можно задать через `--env`, `--env-file .env` или файл `.env`
в рабочей папке (подхватывается автоматически через `python-dotenv`).

Запуск:

```bash
./src/main.py --foreground   # цикл foreground (опрос сервера каждые POLL_INTERVAL сек, по умолчанию 300)
./src/main.py                # интерактивный режим
```

Цикл foreground: получает запланированные задачи → `git pull` + переключение на ветку →
копирует задачу в `docs/task.md` → выполняет через AI → коммит (дата коммита берётся из
`get_commit_date <timestamp прошлого коммита>`, если команда есть в PATH) → `push` →
сообщает серверу. Ошибки отправляются на сервер со статусом `error`.

Логи: `~/.baylang/logs/foreground.log` с ротацией, дублируются в stdout (docker).

### Docker

Сборка образа `bayrell/baylang-ai-agent:1.0.0`:

```bash
./build.sh docker
```

Пересоздание контейнера:

```bash
docker stop baylang_agent
docker rm baylang_agent

docker run -d \
    --restart unless-stopped \
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

- `./baylang:/data/home` — домашняя папка (конфиг `config.json`, логи, история)
- `./project:/data/home/project` — проекты для выполнения задач

В контейнере создаётся пользователь `user` (id 1000, домашняя папка `/data/home`),
foreground запускается автоматически. Точка входа — `src/run.sh`: при запуске он
устанавливает `git config --global user.name` / `user.email` из переменных
`GIT_USER_NAME` / `GIT_USER_EMAIL`, **если они заданы**, и затем запускает `main.py`.
