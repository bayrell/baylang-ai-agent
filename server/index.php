<?php

$config = require __DIR__ . '/config.php';

// Basic Auth для всего интерфейса
if (($_SERVER['PHP_AUTH_PW'] ?? '') !== ($config['password'] ?? '')) {
    http_response_code(401);
    header('WWW-Authenticate: Basic realm="BayLang Server"');
    exit('Unauthorized');
}
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
</header>

<nav id="tabs">
  <button class="tab-btn active" data-tab="tasks">Задачи</button>
  <button class="tab-btn" data-tab="projects">Проекты</button>
  <button class="tab-btn" data-tab="agents">Агенты</button>
</nav>

<main>

  <!-- Задачи -->
  <section id="tab-tasks" class="tab active">
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

  <!-- Проекты -->
  <section id="tab-projects" class="tab">
    <form id="project-form" class="item-form">
      <input type="hidden" name="id" value="">
      <input name="name" placeholder="Название" required>
      <input name="api_name" placeholder="API name" required>
      <button class="primary">Сохранить</button>
      <button type="button" class="reset">Сброс</button>
    </form>
    <div id="projects"></div>
  </section>

  <!-- Агенты -->
  <section id="tab-agents" class="tab">
    <form id="agent-form" class="item-form">
      <input type="hidden" name="id" value="">
      <input name="name" placeholder="Название" required>
      <input name="api_name" placeholder="API name" required>
      <button class="primary">Сохранить</button>
      <button type="button" class="reset">Сброс</button>
    </form>
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
    <label>Выполнить не ранее (UTC) <input name="execute_at" type="datetime-local"></label>
    <label>Статус <select name="status"></select></label>
    <div class="dialog-actions">
      <button type="button" id="task-cancel">Отмена</button>
      <button class="primary">Сохранить</button>
    </div>
  </form>
</dialog>

<script src="main.js"></script>
</body>
</html>
