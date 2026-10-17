<?php

require __DIR__ . '/config.php';

$config = config();
check_auth($config);

?>
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BayLang — Task Server</title>
<link rel="stylesheet" href="main.css">
</head>
<body>

<header>
  <h1>BayLang <small>Task Server</small></h1>
  <button id="btn-settings" title="Настройки">⚙️</button>
</header>

<main>

  <!-- Задачи -->
  <section id="view-tasks" class="view active">
    <div class="toolbar">
      <input id="f-name" type="search" placeholder="🔍 Поиск по названию">
      <select id="f-status"><option value="">Все статусы</option></select>
      <select id="f-agent"><option value="">Все агенты</option></select>
      <select id="f-project"><option value="">Все проекты</option></select>
      <button id="btn-task-add" class="primary">+ Задача</button>
    </div>
    <div id="tasks"></div>
    <div id="pager" class="pager"></div>
  </section>

  <!-- Настройки: меню -->
  <section id="view-settings" class="view">
    <button class="back" data-view="tasks">← Назад</button>
    <h2>Настройки</h2>
    <div class="settings-menu">
      <button data-view="projects">📁 Проекты</button>
      <button data-view="agents">🤖 Агенты</button>
    </div>
  </section>

  <!-- Проекты -->
  <section id="view-projects" class="view">
    <button class="back" data-view="settings">← Назад</button>
    <div class="table-header">
      <h2>Проекты</h2>
      <button id="btn-project-add" class="primary">+ Добавить</button>
    </div>
    <div id="projects"></div>
  </section>

  <!-- Агенты -->
  <section id="view-agents" class="view">
    <button class="back" data-view="settings">← Назад</button>
    <div class="table-header">
      <h2>Агенты</h2>
      <button id="btn-agent-add" class="primary">+ Добавить</button>
    </div>
    <div id="agents"></div>
  </section>

</main>

<!-- Диалог задачи -->
<dialog id="task-dialog">
  <form id="task-form" class="form">
    <h2 id="task-dialog-title">Задача</h2>
    <input type="hidden" name="id">
    <label>Название <input name="name" required></label>
    <label>Проект <select name="project_id" required></select></label>
    <label>Агент <select name="agent_id" required></select></label>
    <label>Ветка <input name="branch" placeholder="main"></label>
    <label>Выполнить не ранее <input name="execute_at" type="datetime-local"></label>
    <label>Статус <select name="status"></select></label>
    <label>Задание (docs/task.md)
      <textarea name="content" rows="10" placeholder="Markdown-описание задания для агента..."></textarea>
    </label>
    <div class="dialog-actions">
      <button type="button" id="task-cancel">Отмена</button>
      <button class="primary">Сохранить</button>
    </div>
  </form>
</dialog>

<!-- Диалог проекта -->
<dialog id="project-dialog">
  <form id="project-form" class="form">
    <h2 id="project-dialog-title">Проект</h2>
    <input type="hidden" name="id">
    <label>Название <input name="name" required></label>
    <label>API name <input name="api_name" required></label>
    <label>Ветка по умолчанию <input name="branch" placeholder="main"></label>
    <div class="dialog-actions">
      <button type="button" id="project-cancel">Отмена</button>
      <button class="primary">Сохранить</button>
    </div>
  </form>
</dialog>

<!-- Диалог агента -->
<dialog id="agent-dialog">
  <form id="agent-form" class="form">
    <h2 id="agent-dialog-title">Агент</h2>
    <input type="hidden" name="id">
    <label>Название <input name="name" required></label>
    <label>API name <input name="api_name" required></label>
    <div class="dialog-actions">
      <button type="button" id="agent-cancel">Отмена</button>
      <button class="primary">Сохранить</button>
    </div>
  </form>
</dialog>

<script src="main.js"></script>
</body>
</html>
