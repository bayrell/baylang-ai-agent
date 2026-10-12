# BayLang AI

Система foreground-выполнения задач: сервер (PHP + SQLite) раздаёт задачи агентам,
клиент (Python) опрашивает сервер раз в 5 минут и выполняет задачи через AI.

## Структура

- `server/` — сервер задач (PHP): `api.php`, `index.php`, `config.php`, `main.css`, `main.js`
- `src/` — AI-клиент: `main.py`, `app.py`, `foreground.py`
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

### API

- `GET  api.php?action=tasks` — задачи (фильтры: `status`, `agent_id`, `project_id`, `name`, `page`, `per_page`)
- `POST api.php?action=task_save` — создать/обновить задачу
- `POST api.php?action=task_delete` — удалить задачу
- `GET  api.php?action=projects|agents` — списки, `POST .../project_save|agent_save|..._delete`
- `GET  api.php?action=plan&agent=<api_name>` — запланированные задачи агента
- `POST api.php?action=task_start|task_done|task_error` — статусы для агента

Статусы задач: `draft` (Черновик), `planned` (Запланирован), `running` (Выполняется),
`done` (Выполнен), `error` (Ошибка).

## Клиент

Конфигурация в `~/.baylang/config.json`:

```json
{
  "server": "http://localhost:8080",
  "password": "admin",
  "agent": "agent-1",
  "projects": {
    "baylang": "/data/projects/baylang"
  }
}
```

- `agent` — api name агента на сервере
- `projects` — соответствие api name проекта и локального пути

Запуск:

```bash
./src/main.py --foreground   # цикл foreground (опрос сервера каждые 5 минут)
./src/main.py                # интерактивный режим
```

Цикл foreground: получает запланированные задачи → `git pull` + переключение на ветку →
копирует задачу в `docs/task.md` → выполняет через AI → коммит (дата коммита берётся из
`get_commit_date <timestamp прошлого коммита>`, если команда есть в PATH) → `push` →
сообщает серверу. Ошибки отправляются на сервер со статусом `error`.

Логи: `~/.baylang/logs/foreground.log` с ротацией, дублируются в stdout (docker).

### Docker

```bash
docker build -t baylang-agent .
docker run --env-file .env -v /data/projects:/data/projects baylang-agent
```

В контейнере создаётся пользователь `user` (id 1000, домашняя папка `/data/home`),
foreground запускается автоматически.

## Итог

Реализована минимальная, но полная система foreground-задач: PHP-сервер с SQLite,
AJAX-интерфейс с фильтрами и пагинацией, Python-клиент с циклом выполнения задач через AI,
Docker-контейнер и ротируемое логирование. Каждый агент получает только свои задачи,
а сервер хранит статусы и ошибки выполнения.
