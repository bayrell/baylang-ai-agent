"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const STATUSES = {
  draft: "Черновик",
  planned: "Запланирован",
  running: "Выполняется",
  done: "Выполнен",
  error: "Ошибка",
};

const PER_PAGE = 20;

let page = 1;
let projects = [];
let agents = [];
let tasksById = {};

// ---------- API ----------

async function api(action, params = {}, body = null) {
  const url = new URL("api.php", location.href);
  url.searchParams.set("action", action);
  for (const [k, v] of Object.entries(params)) {
    if (v !== "" && v !== null && v !== undefined) url.searchParams.set(k, v);
  }
  const opts = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.error) throw new Error(data.error || res.statusText);
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fillSelect(sel, items, emptyLabel) {
  const cur = sel.value;
  sel.innerHTML =
    (emptyLabel ? `<option value="">${emptyLabel}</option>` : "") +
    items.map((i) => `<option value="${i.id}">${esc(i.name)}</option>`).join("");
  if ([...sel.options].some((o) => o.value === cur)) sel.value = cur;
}

// ---------- Навигация (страницы) ----------

function showView(name) {
  $$(".view").forEach((v) => v.classList.remove("active"));
  const view = $("#view-" + name);
  if (view) view.classList.add("active");
}

// ---------- Задачи ----------

async function loadTasks() {
  let data;
  try {
    data = await api("tasks", {
      status: $("#f-status").value,
      agent_id: $("#f-agent").value,
      project_id: $("#f-project").value,
      name: $("#f-name").value.trim(),
      page,
      per_page: PER_PAGE,
    });
  } catch (e) {
    $("#tasks").innerHTML = `<p class="empty">Ошибка: ${esc(e.message)}</p>`;
    return;
  }

  page = data.page;
  tasksById = Object.fromEntries(data.items.map((t) => [t.id, t]));

  $("#tasks").innerHTML = data.items.length
    ? data.items.map((t) => `
      <div class="task">
        <div class="task-main">
          <div class="task-title">${esc(t.name)}
            <span class="badge st-${esc(t.status)}">${STATUSES[t.status] || esc(t.status)}</span>
          </div>
          <div class="task-meta">
            📁 ${esc(t.project_name)} · 🤖 ${esc(t.agent_name)} ·
            🌿 ${esc(t.branch || "—")} · 🕒 ${esc(t.execute_at || "сразу")}
          </div>
          ${t.status === "error" && t.error ? `<div class="task-error">⚠️ ${esc(t.error)}</div>` : ""}
        </div>
        <div class="task-actions">
          <button data-edit="${t.id}" title="Редактировать">✏️</button>
          <button data-del="${t.id}" title="Удалить">🗑</button>
        </div>
      </div>`).join("")
    : '<p class="empty">Нет задач</p>';

  $("#pager").innerHTML = data.pages > 1
    ? `<button data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>‹</button>
       <span>${page} / ${data.pages}</span>
       <button data-page="${page + 1}" ${page >= data.pages ? "disabled" : ""}>›</button>`
    : "";
}

function openTask(t = null) {
  const f = $("#task-form").elements;
  f.id.value = t?.id ?? "";
  f.name.value = t?.name ?? "";
  f.project_id.value = t?.project_id ?? projects[0]?.id ?? "";
  f.agent_id.value = t?.agent_id ?? agents[0]?.id ?? "";
  f.branch.value = t?.branch ?? "";
  f.execute_at.value = t?.execute_at ? t.execute_at.slice(0, 16).replace(" ", "T") : "";
  f.status.value = t?.status ?? "draft";
  f.content.value = t?.content ?? "";
  $("#task-dialog-title").textContent = t ? `Задача` : "Новая задача";
  $("#task-dialog").showModal();
}

async function deleteTask(id) {
  if (!confirm(`Удалить задачу?`)) return;
  try {
    await api("task_delete", {}, { id });
    loadTasks();
  } catch (e) {
    alert(e.message);
  }
}

// ---------- Проекты / Агенты (таблицы + диалоги) ----------

function tableHtml(items, prefix) {
  return items.length
    ? `
    <table class="data-table">
      <thead>
        <tr><th>Название</th><th>API name</th><th class="col-actions">Действия</th></tr>
      </thead>
      <tbody>
        ${items.map((i) => `
        <tr>
          <td>${esc(i.name)}</td>
          <td><code>${esc(i.api_name)}</code></td>
          <td class="col-actions">
            <button data-${prefix}-edit="${i.id}" title="Редактировать">✏️</button>
            <button data-${prefix}-del="${i.id}" title="Удалить">🗑</button>
          </td>
        </tr>`).join("")}
      </tbody>
    </table>`
    : '<p class="empty">Пусто</p>';
}

async function loadProjects() {
  try {
    projects = await api("projects");
  } catch (e) {
    projects = [];
  }
  $("#projects").innerHTML = tableHtml(projects, "p");
  fillSelect($("#f-project"), projects, "Все проекты");
  fillSelect($("#task-form").elements.project_id, projects, "");
}

async function loadAgents() {
  try {
    agents = await api("agents");
  } catch (e) {
    agents = [];
  }
  $("#agents").innerHTML = tableHtml(agents, "a");
  fillSelect($("#f-agent"), agents, "Все агенты");
  fillSelect($("#task-form").elements.agent_id, agents, "");
}

function openItemDialog(dialogSel, titleSel, item) {
  const f = $(dialogSel + " form").elements;
  f.id.value = item?.id ?? "";
  f.name.value = item?.name ?? "";
  f.api_name.value = item?.api_name ?? "";
  $(titleSel).textContent = item ? `${item.name}` : "Новый";
  $(dialogSel).showModal();
  f.name.focus();
}

function bindItemDialog(opts) {
  // opts: {dialog, form, title, listSel, prefix, load, saveAction, delAction, items}
  const form = $(opts.form);
  $(opts.dialog + " " + opts.cancel).onclick = () => $(opts.dialog).close();

  form.onsubmit = async (e) => {
    e.preventDefault();
    const el = form.elements;
    try {
      await api(opts.saveAction, {}, {
        id: el.id.value || 0,
        name: el.name.value,
        api_name: el.api_name.value,
      });
      $(opts.dialog).close();
      opts.load();
    } catch (err) {
      alert(err.message);
    }
  };

  $(opts.listSel).onclick = async (e) => {
    const edit = e.target.closest(`[data-${opts.prefix}-edit]`);
    const del = e.target.closest(`[data-${opts.prefix}-del]`);
    if (edit) {
      const item = opts.items().find((i) => i.id == edit.dataset[`${opts.prefix}Edit`]);
      if (item) openItemDialog(opts.dialog, opts.title, item);
    }
    if (del) {
      const id = +del.dataset[`${opts.prefix}Del`];
      if (!confirm(`Удалить?`)) return;
      try {
        await api(opts.delAction, {}, { id });
        opts.load();
      } catch (err) {
        alert(err.message);
      }
    }
  };
}

// ---------- Инициализация ----------

function init() {
  // навигация по страницам (кнопки "назад", меню настроек, шестерёнка)
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-view]");
    if (btn) showView(btn.dataset.view);
  });
  $("#btn-settings").onclick = () => showView("settings");

  // статусы
  $("#f-status").innerHTML +=
    Object.entries(STATUSES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  $("#task-form").elements.status.innerHTML =
    Object.entries(STATUSES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");

  // фильтры
  ["#f-status", "#f-agent", "#f-project"].forEach((s) => {
    $(s).onchange = () => { page = 1; loadTasks(); };
  });
  let timer;
  $("#f-name").oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(() => { page = 1; loadTasks(); }, 400);
  };

  // задачи
  $("#btn-task-add").onclick = () => openTask();
  $("#tasks").onclick = (e) => {
    const edit = e.target.closest("[data-edit]");
    const del = e.target.closest("[data-del]");
    if (edit) openTask(tasksById[edit.dataset.edit]);
    if (del) deleteTask(+del.dataset.del);
  };
  $("#pager").onclick = (e) => {
    const b = e.target.closest("[data-page]");
    if (b && !b.disabled) { page = +b.dataset.page; loadTasks(); }
  };
  $("#task-cancel").onclick = () => $("#task-dialog").close();
  $("#task-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target.elements;
    try {
      await api("task_save", {}, {
        id: f.id.value || 0,
        name: f.name.value,
        project_id: f.project_id.value,
        agent_id: f.agent_id.value,
        branch: f.branch.value,
        execute_at: f.execute_at.value,
        status: f.status.value,
        content: f.content.value,
      });
      $("#task-dialog").close();
      loadTasks();
    } catch (err) {
      alert(err.message);
    }
  };

  // проекты
  $("#btn-project-add").onclick = () => openItemDialog("#project-dialog", "#project-dialog-title", null);
  bindItemDialog({
    dialog: "#project-dialog",
    form: "#project-form",
    title: "#project-dialog-title",
    cancel: "#project-cancel",
    listSel: "#projects",
    prefix: "p",
    load: loadProjects,
    items: () => projects,
    saveAction: "project_save",
    delAction: "project_delete",
  });

  // агенты
  $("#btn-agent-add").onclick = () => openItemDialog("#agent-dialog", "#agent-dialog-title", null);
  bindItemDialog({
    dialog: "#agent-dialog",
    form: "#agent-form",
    title: "#agent-dialog-title",
    cancel: "#agent-cancel",
    listSel: "#agents",
    prefix: "a",
    load: loadAgents,
    items: () => agents,
    saveAction: "agent_save",
    delAction: "agent_delete",
  });

  // загрузка
  Promise.all([loadProjects(), loadAgents()]).then(loadTasks);
}

init();
