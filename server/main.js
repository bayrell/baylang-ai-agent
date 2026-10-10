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
  $("#task-dialog-title").textContent = t ? `Задача #${t.id}` : "Новая задача";
  $("#task-dialog").showModal();
}

async function deleteTask(id) {
  if (!confirm(`Удалить задачу #${id}?`)) return;
  try {
    await api("task_delete", {}, { id });
    loadTasks();
  } catch (e) {
    alert(e.message);
  }
}

// ---------- Проекты / Агенты ----------

function itemHtml(items, prefix) {
  return items.length
    ? items.map((i) => `
      <div class="item">
        <div><b>${esc(i.name)}</b><code>${esc(i.api_name)}</code></div>
        <div class="item-actions">
          <button data-${prefix}-edit="${i.id}">✏️</button>
          <button data-${prefix}-del="${i.id}">🗑</button>
        </div>
      </div>`).join("")
    : '<p class="empty">Пусто</p>';
}

async function loadProjects() {
  try {
    projects = await api("projects");
  } catch (e) {
    projects = [];
  }
  $("#projects").innerHTML = itemHtml(projects, "p");
  fillSelect($("#f-project"), projects, "Все проекты");
  fillSelect($("#task-form").elements.project_id, projects, "");
}

async function loadAgents() {
  try {
    agents = await api("agents");
  } catch (e) {
    agents = [];
  }
  $("#agents").innerHTML = itemHtml(agents, "a");
  fillSelect($("#f-agent"), agents, "Все агенты");
  fillSelect($("#task-form").elements.agent_id, agents, "");
}

function bindItemForm(form, action, load) {
  form.onsubmit = async (e) => {
    e.preventDefault();
    const el = form.elements;
    try {
      await api(action, {}, {
        id: el.id.value || 0,
        name: el.name.value,
        api_name: el.api_name.value,
      });
      form.reset();
      el.id.value = "";
      load();
    } catch (err) {
      alert(err.message);
    }
  };
  $(".reset", form).onclick = () => {
    form.reset();
    form.elements.id.value = "";
  };
}

function bindItemList(listSel, prefix, form, load, delAction) {
  $(listSel).onclick = async (e) => {
    const edit = e.target.closest(`[data-${prefix}-edit]`);
    const del = e.target.closest(`[data-${prefix}-del]`);
    if (edit) {
      const item = (prefix === "p" ? projects : agents).find((i) => i.id == edit.dataset[`${prefix}Edit`]);
      if (item) {
        form.elements.id.value = item.id;
        form.elements.name.value = item.name;
        form.elements.api_name.value = item.api_name;
        form.elements.name.focus();
      }
    }
    if (del) {
      const id = +del.dataset[`${prefix}Del`];
      if (!confirm(`Удалить #${id}?`)) return;
      try {
        await api(delAction, {}, { id });
        load();
      } catch (err) {
        alert(err.message);
      }
    }
  };
}

// ---------- Инициализация ----------

function init() {
  // вкладки
  $$(".tab-btn").forEach((b) => {
    b.onclick = () => {
      $$(".tab-btn").forEach((x) => x.classList.remove("active"));
      $$(".tab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      $("#tab-" + b.dataset.tab).classList.add("active");
    };
  });

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
      });
      $("#task-dialog").close();
      loadTasks();
    } catch (err) {
      alert(err.message);
    }
  };

  // проекты и агенты
  const pf = $("#project-form");
  const af = $("#agent-form");
  bindItemForm(pf, "project_save", loadProjects);
  bindItemForm(af, "agent_save", loadAgents);
  bindItemList("#projects", "p", pf, loadProjects, "project_delete");
  bindItemList("#agents", "a", af, loadAgents, "agent_delete");

  // загрузка
  Promise.all([loadProjects(), loadAgents()]).then(loadTasks);
}

init();
