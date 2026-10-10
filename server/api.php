<?php

/**
 * BayLang Task Server — простой REST API (SQLite через PDO)
 *
 * GET  action=tasks          — список задач (фильтры: status, agent_id, project_id, name, page, per_page)
 * POST action=task_save      — создать/обновить задачу {id?, name, project_id, agent_id, branch, execute_at, status}
 * POST action=task_delete    — удалить задачу {id}
 *
 * GET  action=projects       — список проектов
 * POST action=project_save   — создать/обновить проект {id?, name, api_name}
 * POST action=project_delete — удалить проект {id}
 *
 * GET  action=agents         — список агентов
 * POST action=agent_save     — создать/обновить агента {id?, name, api_name}
 * POST action=agent_delete   — удалить агента {id}
 *
 * GET  action=plan           — запланированные задачи агента (agent=<api_name>)
 * POST action=task_start     — агент берёт задачу {id, agent}
 * POST action=task_done      — задача выполнена {id, agent}
 * POST action=task_error     — ошибка выполнения {id, agent, error}
 */

$config = require __DIR__ . '/config.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

// ---------- Basic Auth ----------
if (($_SERVER['PHP_AUTH_PW'] ?? '') !== ($config['password'] ?? '')) {
    http_response_code(401);
    header('WWW-Authenticate: Basic realm="BayLang Server"');
    exit(json_encode(['error' => 'Unauthorized']));
}

// ---------- База данных (создаётся автоматически) ----------
$db = new PDO('sqlite:' . ($config['db'] ?? __DIR__ . '/data.sqlite'));
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
$db->exec('PRAGMA journal_mode=WAL');
$db->exec('PRAGMA foreign_keys=ON');
$db->exec('
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    api_name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    api_name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    branch TEXT NOT NULL DEFAULT \'\',
    execute_at TEXT,
    status TEXT NOT NULL DEFAULT \'draft\',
    error TEXT NOT NULL DEFAULT \'\',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
');

const STATUSES = ['draft', 'planned', 'running', 'done', 'error'];

$now = gmdate('Y-m-d H:i:s');
$action = $_GET['action'] ?? '';
$body = json_decode(file_get_contents('php://input') ?: 'null', true) ?: [];

function out($data): void {
    exit(json_encode($data, JSON_UNESCAPED_UNICODE));
}

try {
    switch (($_SERVER['REQUEST_METHOD'] ?? 'GET') . ' ' . $action) {

        // ---------- Задачи (для UI) ----------

        case 'GET tasks': {
            $status = trim($_GET['status'] ?? '');
            $agent_id = (int)($_GET['agent_id'] ?? 0);
            $project_id = (int)($_GET['project_id'] ?? 0);
            $name = trim($_GET['name'] ?? '');
            $page = max(1, (int)($_GET['page'] ?? 1));
            $per_page = max(1, min(100, (int)($_GET['per_page'] ?? 20)));

            $where = [];
            $params = [];
            if ($status !== '' && in_array($status, STATUSES, true)) {
                $where[] = 't.status = ?';
                $params[] = $status;
            }
            if ($agent_id > 0) {
                $where[] = 't.agent_id = ?';
                $params[] = $agent_id;
            }
            if ($project_id > 0) {
                $where[] = 't.project_id = ?';
                $params[] = $project_id;
            }
            if ($name !== '') {
                $where[] = 't.name LIKE ?';
                $params[] = "%$name%";
            }
            $where_sql = $where ? 'WHERE ' . implode(' AND ', $where) : '';

            $stmt = $db->prepare("SELECT COUNT(*) AS c FROM tasks t $where_sql");
            $stmt->execute($params);
            $total = (int)$stmt->fetch()['c'];
            $pages = max(1, (int)ceil($total / $per_page));
            $page = min($page, $pages);

            $stmt = $db->prepare("
                SELECT t.*, p.name AS project_name, a.name AS agent_name
                FROM tasks t
                LEFT JOIN projects p ON p.id = t.project_id
                LEFT JOIN agents a ON a.id = t.agent_id
                $where_sql
                ORDER BY t.id DESC
                LIMIT ? OFFSET ?
            ");
            $stmt->execute([...$params, $per_page, ($page - 1) * $per_page]);

            out(['items' => $stmt->fetchAll(), 'total' => $total, 'page' => $page, 'pages' => $pages]);
        }

        case 'POST task_save': {
            $id = (int)($body['id'] ?? 0);
            $name = trim($body['name'] ?? '');
            $project_id = (int)($body['project_id'] ?? 0);
            $agent_id = (int)($body['agent_id'] ?? 0);
            $branch = trim($body['branch'] ?? '');
            $status = in_array($body['status'] ?? '', STATUSES, true) ? $body['status'] : 'draft';

            $execute_at = trim(str_replace('T', ' ', (string)($body['execute_at'] ?? '')));
            if ($execute_at === '') {
                $execute_at = null;
            } elseif (strlen($execute_at) === 16) {
                $execute_at .= ':00'; // приводим к y-m-d h:i:s
            }

            if ($name === '' || $project_id <= 0 || $agent_id <= 0) {
                http_response_code(400);
                out(['error' => 'Обязательные поля: name, project_id, agent_id']);
            }

            if ($id > 0) {
                $db->prepare('UPDATE tasks SET name=?, project_id=?, agent_id=?, branch=?, execute_at=?, status=?, updated_at=? WHERE id=?')
                    ->execute([$name, $project_id, $agent_id, $branch, $execute_at, $status, $now, $id]);
            } else {
                $db->prepare('INSERT INTO tasks (name, project_id, agent_id, branch, execute_at, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)')
                    ->execute([$name, $project_id, $agent_id, $branch, $execute_at, $status, $now, $now]);
                $id = (int)$db->lastInsertId();
            }
            out(['id' => $id]);
        }

        case 'POST task_delete': {
            $db->prepare('DELETE FROM tasks WHERE id = ?')->execute([(int)($body['id'] ?? 0)]);
            out(['ok' => true]);
        }

        // ---------- Проекты ----------

        case 'GET projects': {
            out($db->query('SELECT * FROM projects ORDER BY name')->fetchAll());
        }

        case 'POST project_save': {
            $id = (int)($body['id'] ?? 0);
            $name = trim($body['name'] ?? '');
            $api_name = trim($body['api_name'] ?? '');
            if ($name === '' || $api_name === '') {
                http_response_code(400);
                out(['error' => 'Обязательные поля: name, api_name']);
            }
            if ($id > 0) {
                $db->prepare('UPDATE projects SET name=?, api_name=? WHERE id=?')->execute([$name, $api_name, $id]);
            } else {
                $db->prepare('INSERT INTO projects (name, api_name) VALUES (?,?)')->execute([$name, $api_name]);
                $id = (int)$db->lastInsertId();
            }
            out(['id' => $id]);
        }

        case 'POST project_delete': {
            $id = (int)($body['id'] ?? 0);
            $count = $db->prepare('SELECT COUNT(*) FROM tasks WHERE project_id = ?');
            $count->execute([$id]);
            if ((int)$count->fetchColumn() > 0) {
                http_response_code(400);
                out(['error' => 'Нельзя удалить: у проекта есть задачи']);
            }
            $db->prepare('DELETE FROM projects WHERE id = ?')->execute([$id]);
            out(['ok' => true]);
        }

        // ---------- Агенты ----------

        case 'GET agents': {
            out($db->query('SELECT * FROM agents ORDER BY name')->fetchAll());
        }

        case 'POST agent_save': {
            $id = (int)($body['id'] ?? 0);
            $name = trim($body['name'] ?? '');
            $api_name = trim($body['api_name'] ?? '');
            if ($name === '' || $api_name === '') {
                http_response_code(400);
                out(['error' => 'Обязательные поля: name, api_name']);
            }
            if ($id > 0) {
                $db->prepare('UPDATE agents SET name=?, api_name=? WHERE id=?')->execute([$name, $api_name, $id]);
            } else {
                $db->prepare('INSERT INTO agents (name, api_name) VALUES (?,?)')->execute([$name, $api_name]);
                $id = (int)$db->lastInsertId();
            }
            out(['id' => $id]);
        }

        case 'POST agent_delete': {
            $id = (int)($body['id'] ?? 0);
            $count = $db->prepare('SELECT COUNT(*) FROM tasks WHERE agent_id = ?');
            $count->execute([$id]);
            if ((int)$count->fetchColumn() > 0) {
                http_response_code(400);
                out(['error' => 'Нельзя удалить: у агента есть задачи']);
            }
            $db->prepare('DELETE FROM agents WHERE id = ?')->execute([$id]);
            out(['ok' => true]);
        }

        // ---------- Для агента (foreground) ----------

        case 'GET plan': {
            $agent = trim($_GET['agent'] ?? '');
            $stmt = $db->prepare("
                SELECT t.*, p.api_name AS project_api_name, p.name AS project_name, ag.api_name AS agent_api_name
                FROM tasks t
                JOIN agents ag ON ag.id = t.agent_id
                JOIN projects p ON p.id = t.project_id
                WHERE ag.api_name = ? AND t.status = 'planned'
                  AND (t.execute_at IS NULL OR t.execute_at <= ?)
                ORDER BY t.id ASC
            ");
            $stmt->execute([$agent, $now]);
            out($stmt->fetchAll());
        }

        case 'POST task_start': {
            $stmt = $db->prepare("
                UPDATE tasks SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'planned'
                  AND agent_id = (SELECT id FROM agents WHERE api_name = ?)
            ");
            $stmt->execute([$now, (int)($body['id'] ?? 0), trim($body['agent'] ?? '')]);
            out(['ok' => $stmt->rowCount() > 0]);
        }

        case 'POST task_done': {
            $stmt = $db->prepare("
                UPDATE tasks SET status = 'done', error = '', updated_at = ?
                WHERE id = ? AND agent_id = (SELECT id FROM agents WHERE api_name = ?)
            ");
            $stmt->execute([$now, (int)($body['id'] ?? 0), trim($body['agent'] ?? '')]);
            out(['ok' => $stmt->rowCount() > 0]);
        }

        case 'POST task_error': {
            $stmt = $db->prepare("
                UPDATE tasks SET status = 'error', error = ?, updated_at = ?
                WHERE id = ? AND agent_id = (SELECT id FROM agents WHERE api_name = ?)
            ");
            $stmt->execute([
                mb_substr(trim($body['error'] ?? ''), 0, 2000),
                $now,
                (int)($body['id'] ?? 0),
                trim($body['agent'] ?? ''),
            ]);
            out(['ok' => $stmt->rowCount() > 0]);
        }

        default: {
            http_response_code(404);
            out(['error' => 'Unknown action']);
        }
    }
} catch (PDOException $e) {
    http_response_code(400);
    out(['error' => $e->getMessage()]);
}
