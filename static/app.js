// =====================================================
// Household Tracker - front-end logic (v2 with sections)
// =====================================================

const POLL_MS = 3000;
const STATUS_EL = document.getElementById("status");
const COLLAPSED_KEY = "household-tracker-collapsed";

const LISTS = ["todos", "groceries"];

function setStatus(msg, isError = false) {
  STATUS_EL.textContent = msg;
  STATUS_EL.style.color = isError ? "var(--danger)" : "var(--fg-muted)";
  if (msg && !isError) {
    setTimeout(() => {
      if (STATUS_EL.textContent === msg) STATUS_EL.textContent = "";
    }, 2000);
  }
}

// ---------- Theme ----------
const THEME_KEY = "household-tracker-theme";
const themeSelect = document.getElementById("theme-select");

function applyTheme(name) {
  document.documentElement.setAttribute("data-theme", name);
  themeSelect.value = name;
}

themeSelect.addEventListener("change", (e) => {
  const t = e.target.value;
  localStorage.setItem(THEME_KEY, t);
  applyTheme(t);
});

applyTheme(localStorage.getItem(THEME_KEY) || "terminal");

// ---------- Collapsed-section persistence (per device) ----------
function getCollapsedSet() {
  try {
    return new Set(JSON.parse(localStorage.getItem(COLLAPSED_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveCollapsedSet(set) {
  localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...set]));
}

function collapsedKey(listName, sectionId) {
  return `${listName}:${sectionId}`;
}

function isCollapsed(listName, sectionId) {
  return getCollapsedSet().has(collapsedKey(listName, sectionId));
}

function setCollapsed(listName, sectionId, collapsed) {
  const set = getCollapsedSet();
  const key = collapsedKey(listName, sectionId);
  if (collapsed) set.add(key);
  else set.delete(key);
  saveCollapsedSet(set);
}

// ---------- API ----------
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ---------- State ----------
const state = {
  todos: { sections: [], items: [] },
  groceries: { sections: [], items: [] },
};

// ---------- Rendering ----------
function renderSectionSelect(listName) {
  const sel = document.querySelector(
    `.section-select[data-list="${listName}"]`,
  );
  const currentValue = sel.value;
  sel.innerHTML = "";
  for (const s of state[listName].sections) {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.name;
    sel.appendChild(opt);
  }
  // Restore prior selection if still valid (so re-renders don't reset the picker).
  if (
    currentValue &&
    state[listName].sections.some((s) => String(s.id) === currentValue)
  ) {
    sel.value = currentValue;
  }
}

function renderList(listName) {
  const container = document.getElementById(`${listName}-sections`);
  const { sections, items } = state[listName];

  // Group items by section.
  const bySection = new Map();
  for (const s of sections) bySection.set(s.id, []);
  for (const it of items) {
    if (bySection.has(it.section_id)) bySection.get(it.section_id).push(it);
  }

  container.innerHTML = "";

  for (const section of sections) {
    const secItems = bySection.get(section.id) || [];
    // Hide the default Uncategorized section entirely when empty -- keeps the UI clean
    // when the user has organized everything into real sections.
    if (section.is_default && secItems.length === 0) continue;

    const secEl = document.createElement("div");
    secEl.className = "section";
    if (isCollapsed(listName, section.id)) secEl.classList.add("collapsed");

    // Header
    const header = document.createElement("div");
    header.className = "section-header";

    const toggle = document.createElement("button");
    toggle.className = "section-toggle";
    toggle.type = "button";
    toggle.title = "collapse / expand";
    toggle.addEventListener("click", () => {
      const nowCollapsed = !secEl.classList.contains("collapsed");
      secEl.classList.toggle("collapsed");
      setCollapsed(listName, section.id, nowCollapsed);
    });

    const nameEl = document.createElement("span");
    nameEl.className = "section-name";
    nameEl.textContent = section.name;
    if (!section.is_default) {
      nameEl.title = "click to rename";
      nameEl.addEventListener("click", () =>
        beginRename(listName, section, nameEl, header),
      );
    }

    const count = document.createElement("span");
    count.className = "section-count";
    const open = secItems.filter((i) => !i.done).length;
    count.textContent = `(${open}/${secItems.length})`;

    header.append(toggle, nameEl, count);

    if (!section.is_default) {
      const del = document.createElement("button");
      del.className = "section-delete-btn";
      del.type = "button";
      del.textContent = "✕";
      del.title = "delete section (items move to Uncategorized)";
      del.addEventListener("click", () => deleteSection(listName, section));
      header.append(del);
    }

    secEl.appendChild(header);

    // Items
    const ul = document.createElement("ul");
    ul.className = "items";

    if (secItems.length === 0) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "// empty";
      ul.appendChild(li);
    } else {
      // Open items first, done at bottom -- sorted on server but groups
      // can interleave them; resort within the group.
      secItems.sort((a, b) => {
        if (a.done !== b.done) return a.done ? 1 : -1;
        return a.id - b.id;
      });

      for (const item of secItems) {
        const li = document.createElement("li");
        if (item.done) li.classList.add("done");

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "checkbox";
        checkbox.checked = item.done;
        checkbox.addEventListener("change", () =>
          toggleItem(listName, item.id),
        );

        const text = document.createElement("span");
        text.className = "item-text";
        text.textContent = item.text;

        const delBtn = document.createElement("button");
        delBtn.className = "delete-btn";
        delBtn.textContent = "✕";
        delBtn.title = "delete";
        delBtn.addEventListener("click", () => deleteItem(listName, item.id));

        li.append(checkbox, text, delBtn);
        ul.appendChild(li);
      }
    }

    secEl.appendChild(ul);
    container.appendChild(secEl);
  }

  // If nothing rendered at all (all sections empty, default hidden), show a hint.
  if (container.children.length === 0) {
    const hint = document.createElement("div");
    hint.className = "section";
    hint.innerHTML = `<div class="section-header"><span class="section-name" style="cursor:default">// ${listName === "todos" ? "no tasks" : "nothing to buy"}</span></div>`;
    container.appendChild(hint);
  }
}

function beginRename(listName, section, nameEl, header) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "section-name-input";
  input.value = section.name;
  input.maxLength = 50;

  const commit = async (save) => {
    const newName = input.value.trim();
    input.replaceWith(nameEl);
    if (!save || !newName || newName === section.name) return;
    try {
      await api(`/api/${listName}/sections/${section.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: newName }),
      });
      await refreshList(listName);
      setStatus("section renamed");
    } catch (err) {
      setStatus(`rename failed: ${err.message}`, true);
    }
  };

  input.addEventListener("blur", () => commit(true));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit(true);
    }
    if (e.key === "Escape") {
      commit(false);
    }
  });

  nameEl.replaceWith(input);
  input.focus();
  input.select();
}

// ---------- Data ops ----------
async function refreshList(listName) {
  try {
    const [sections, items] = await Promise.all([
      api(`/api/${listName}/sections`),
      api(`/api/${listName}`),
    ]);
    const next = { sections, items };
    // Skip if nothing changed (reduces flicker during polling).
    if (JSON.stringify(next) === JSON.stringify(state[listName])) return;
    state[listName] = next;
    renderSectionSelect(listName);
    renderList(listName);
  } catch (err) {
    setStatus(`error loading ${listName}: ${err.message}`, true);
  }
}

async function addItem(listName, text, sectionId) {
  try {
    const body = { text };
    if (sectionId) body.section_id = Number(sectionId);
    await api(`/api/${listName}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    await refreshList(listName);
  } catch (err) {
    setStatus(`error: ${err.message}`, true);
  }
}

async function toggleItem(listName, id) {
  try {
    await api(`/api/${listName}/${id}/toggle`, { method: "POST" });
    await refreshList(listName);
  } catch (err) {
    setStatus(`error: ${err.message}`, true);
  }
}

async function deleteItem(listName, id) {
  try {
    await api(`/api/${listName}/${id}`, { method: "DELETE" });
    await refreshList(listName);
  } catch (err) {
    setStatus(`error: ${err.message}`, true);
  }
}

async function addSection(listName) {
  const name = prompt(`new section in ${listName}:`);
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed) return;
  try {
    await api(`/api/${listName}/sections`, {
      method: "POST",
      body: JSON.stringify({ name: trimmed }),
    });
    await refreshList(listName);
    setStatus(`section added`);
  } catch (err) {
    setStatus(`error: ${err.message}`, true);
  }
}

async function deleteSection(listName, section) {
  const ok = confirm(
    `Delete section "${section.name}"?\n\n` +
      `Items inside will move to Uncategorized (they won't be lost).`,
  );
  if (!ok) return;
  try {
    await api(`/api/${listName}/sections/${section.id}`, { method: "DELETE" });
    await refreshList(listName);
    setStatus("section deleted");
  } catch (err) {
    setStatus(`error: ${err.message}`, true);
  }
}

// ---------- Wiring ----------
document.querySelectorAll(".add-form").forEach((form) => {
  const listName = form.dataset.list;
  const input = form.querySelector(".item-input");
  const select = form.querySelector(".section-select");

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addItem(listName, text, select.value);
  });
});

document.querySelectorAll(".add-section-btn").forEach((btn) => {
  btn.addEventListener("click", () => addSection(btn.dataset.list));
});

// ---------- Initial load + polling ----------
for (const l of LISTS) refreshList(l);
setInterval(() => {
  for (const l of LISTS) refreshList(l);
}, POLL_MS);
