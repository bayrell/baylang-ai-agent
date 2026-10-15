# BayLang AI

**BayLang AI** — a task execution system for AI agents. The server
distributes tasks to agents, while the client polls the server every
`POLL_INTERVAL` seconds (default: 300) and executes tasks through AI (OpenRouter).

Project goals:

- **Distribute tasks** among agents: planning, statuses, assignment to an agent and project
- **Automatically execute tasks via AI**: `git pull` → copy the task into `docs/task.md`
  → execution → commit → `push` → report back to the server
- **Provide a web interface** for managing tasks, projects and agents (AJAX, mobile-friendly)

## Running the Docker container

Building the image `bayrell/baylang-ai-agent:1.0.0`:

```bash
./build.sh docker
```

Running the container:

```bash
docker run -d \
    --restart unless-stopped \
    --env OPENROUTER_API_KEY="" \
    --env OPENROUTER_MODEL="openrouter/auto" \
    --env TZ="Asia/Almaty" \
    --env GIT_USER_NAME="BayLang Agent" \
    --env GIT_USER_EMAIL="agent@baylang" \
    --name baylang_agent \
    -v ./baylang:/data/home \
    -v ./project:/data/home/project \
    bayrell/baylang-ai-agent:1.0.0
```

- `./baylang:/data/home` — home folder (config `config.json`, logs, history)
- `./project:/data/home/project` — projects for task execution

Recreating the container:

```bash
docker stop baylang_agent
docker rm baylang_agent
# then docker run ... (see above)
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | yes | API key for [OpenRouter](https://openrouter.ai/) to access the models |
| `OPENROUTER_MODEL` | yes | The model to use, e.g. `openrouter/auto` |
| `OPENROUTER_PROVIDERS` | no | Comma-separated list of allowed providers |
| `TZ` | no | Time zone, e.g. `Asia/Almaty` |
| `GIT_USER_NAME` | no | `git config --global user.name` for agent commits |
| `GIT_USER_EMAIL` | no | `git config --global user.email` for agent commits |
| `BAYLANG_SERVER` | no | URL of the task server, e.g. `http://localhost:8080` |
| `BAYLANG_LOGIN` | no | Basic auth login for the task server |
| `BAYLANG_PASSWORD` | no | Basic auth password for the task server |
| `BAYLANG_AGENT` | no | Api name of the agent on the task server |
| `BAYLANG_PROJECTS` | no | Projects: JSON `{"api_name": "/path"}` or `api_name=/path, ...` |
| `BAYLANG_PROJECTS_DIR` | no | Path to the projects folder: the api name of a project is its folder name (takes precedence over `config.json`, but yields to `BAYLANG_PROJECTS`) |
| `POLL_INTERVAL` | no | Server polling interval in seconds, default `300` |

The `BAYLANG_*` variables **override** values from `config.json` in memory only:
the file `~/.baylang/config.json` is not modified.

Variables can be set via `--env`, `--env-file .env`, or a `.env` file in the
working folder (picked up automatically via `python-dotenv`).

## Configuration

### Server

Configuration lives in `server/config.php` (basic auth password, path to SQLite).
The database is created automatically. Dates are stored in UTC with the format
`y-m-d h:i:s`; in the UI, time is displayed in the user's time zone and converted
back to UTC on save.

Running (for development):

```bash
php -S 0.0.0.0:8080 -t server
```

UI: `http://localhost:8080/` (basic auth, password from config.php).
Task list with filters (status, agent, project, title), pagination,
CRUD for tasks/projects/agents — all via AJAX without page reloads, mobile-friendly.

### Client

Configuration lives in `~/.baylang/config.json`:

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

- `agent` — api name of the agent on the server
- `projects` — mapping of project api name to a local path

Running (from the project folder):

```bash
./src/main.py --foreground   # foreground loop (polls the server every POLL_INTERVAL sec, default 300)
./src/main.py                # interactive mode
```

Foreground loop: fetches planned tasks → `git pull` + branch switch →
copies the task into `docs/task.md` → executes it via AI → commit (the commit date
is taken from `get_commit_date <previous commit timestamp>`, if the command is in
PATH) → `push` → reports to the server. Errors are sent to the server with status `error`.

Logs: `~/.baylang/logs/foreground.log` with rotation, also mirrored to stdout (docker).

## Project structure

- `server/` — task server (PHP): `api.php`, `index.php`, `config.php`, `main.css`, `main.js`
- `src/` — AI client: `main.py`, `app.py`, `foreground.py`, `run.sh`
- `Dockerfile` — client container (foreground)
- `build.sh` — docker image build (`./build.sh docker`)
