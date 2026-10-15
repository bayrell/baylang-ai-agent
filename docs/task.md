1. **`run_git` без таймаута и без отключения промптов git** (`src/foreground.py:148`).
   `subprocess.run` вызывается без `timeout` — если `git pull`/`push` виснет на сети
   или git запрашивает креды (HTTPS-пароль, SSH-фразу), **foreground зависает навсегда**
   без единой записи в лог. Нужно: `timeout=` в `subprocess.run` и env
   `GIT_TERMINAL_PROMPT=0` (плюс `GIT_SSH_COMMAND=BatchMode=yes`).

2. **`push` новой ветки упадёт без upstream** (`src/foreground.py:288`).
   Если `checkout -B branch` создал ветку локально, `git push` вернёт
   «no upstream branch» → `GitError` → задача уйдёт в `error`, хотя работа сделана.
   Нужен `git push -u origin <branch>`.

3. **Грязное дерево переносится между задачами** (`src/foreground.py:256-263`).
   `git pull` идёт *до* checkout, а при ошибке checkout делается принудительный
   `checkout -B`. Если предыдущая задача упала, оставив изменения в дереве, они
   **вложатся в коммит следующей задачи** (ведь `git add -A`), — кросс-контаминация
   задач. Плюс `pull` идёт не на целевой ветке, то есть ветка задачи обновляется
   не всегда. Логичнее: `fetch` → `checkout` → `pull --ff-only` на целевой ветке,
   а перед этим чистка/reset при грязном дереве.

4. **Некорректный `BAYLANG_PROJECTS`/`config.json` роняет клиент на старте**:
   `parse_projects` при JSON-ошибке бросает `json.JSONDecodeError`, а `load_config`
   при битом `config.json` — тоже; исключение не перехватывается → foreground не
   стартует без понятного сообщения.

5. **`api.php` отдаёт текст исключения PDO** клиенту — раскрывает пути/структуру
    БД (информация для атакующего с кредами). Логировать на сервер, клиенту —
    общее сообщение.

6. **SQLite «database is locked»**: WAL включён, но `busy_timeout` не задан —
    при одновременных запросах UI и агента возможны кратковременные
    `PDOexception`. Достаточно `PRAGMA busy_timeout=5000`.

7. **`httpx.AsyncClient`** (`ServerClient`) — для
    долгоживущего демона не страшно, но при остановке стоило бы `aclose()`
    (и ловить `httpx.HTTPStatusError` отдельно: сейчас 401/500 сервера
    вываливаются в общий `except` цикла как «Ошибка цикла foreground»).

8. **Нет лимита на `GET plan`** — сервер возвращает все planned-задачи разом;
    при большой очереди это O(n) памяти на каждый опрос. `LIMIT` не помешает.

9. wait_commit_date — там dt = int(commit_date), а проверка if dt is None уже после… на самом деле int(None) упадёт до этой проверки. Но commit_date приходит из get_commit_date, который возвращает None либо строку — и судя по вызову if commit_date: перед ожиданием, None не дойдёт