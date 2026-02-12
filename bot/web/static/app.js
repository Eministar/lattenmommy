const $ = (id) => document.getElementById(id);

const state = {
  user: null,
  guilds: [],
  guildId: null,
};

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: Object.assign({ "Content-Type": "application/json" }, opts.headers || {}),
    ...opts,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${txt}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

function setView(view) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  const active = document.getElementById(`view-${view}`);
  if (active) active.classList.remove("hidden");

  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
}

function setAuthState(loggedIn) {
  $("authPanel").classList.toggle("hidden", loggedIn);
  $("userPanel").classList.toggle("hidden", !loggedIn);
  if (loggedIn) {
    setView("overview");
  } else {
    setView("login");
  }
}

function renderGuilds() {
  const list = $("guildList");
  list.innerHTML = "";
  if (!state.guilds.length) {
    list.innerHTML = '<div class="muted">Keine Guilds verfügbar</div>';
    return;
  }
  state.guilds.forEach((g) => {
    const item = document.createElement("div");
    item.className = "guild-item" + (state.guildId === g.id ? " active" : "");
    const icon = document.createElement("div");
    icon.className = "guild-icon";
    if (g.icon) {
      icon.style.backgroundImage = `url(https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png)`;
      icon.style.backgroundSize = "cover";
    }
    const name = document.createElement("div");
    name.textContent = g.name;
    item.appendChild(icon);
    item.appendChild(name);
    item.onclick = () => selectGuild(g.id);
    list.appendChild(item);
  });
}

function selectGuild(guildId) {
  state.guildId = guildId;
  localStorage.setItem("starry_guild", String(guildId));
  renderGuilds();
  const guild = state.guilds.find((g) => g.id === guildId);
  $("selectedGuildLabel").textContent = guild ? `Guild: ${guild.name}` : "Keine Guild gewählt";
  const birthdayLabel = $("birthdayGuildLabel");
  if (birthdayLabel) {
    birthdayLabel.textContent = guild ? `Guild: ${guild.name}` : "Keine Guild gewählt";
  }
  refreshGuildData().catch((e) => toast(e.message));
}

function requireGuild() {
  if (!state.guildId) {
    toast("Bitte erst eine Guild wählen");
    throw new Error("guild_missing");
  }
  return state.guildId;
}

function parseFields(raw) {
  const lines = (raw || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const out = [];
  for (const line of lines) {
    const parts = line.split("|");
    const name = (parts[0] || "").trim();
    const value = (parts[1] || "").trim();
    const inline = ((parts[2] || "").trim().toLowerCase() === "true");
    if (!name || !value) continue;
    out.push({ name, value, inline });
  }
  return out;
}

function statusBadge(status) {
  if (status === "closed") return { text: "geschlossen", cls: "closed" };
  if (status === "claimed") return { text: "geclaimed", cls: "claimed" };
  return { text: "offen", cls: "open" };
}

function renderTickets(list) {
  const root = $("tickets");
  const query = $("ticketSearch").value.trim();
  root.innerHTML = "";
  const rows = list.filter((t) => {
    if (!query) return true;
    return (
      String(t.id).includes(query) ||
      String(t.user_id).includes(query) ||
      String(t.thread_id).includes(query) ||
      String(t.claimed_by || "").includes(query)
    );
  });
  if (!rows.length) {
    root.innerHTML = '<div class="list-item">Keine Tickets.</div>';
    return;
  }
  for (const t of rows) {
    const badge = statusBadge(t.status);
    const div = document.createElement("div");
    div.className = "ticket";
    div.innerHTML = `
      <div class="ticket-row">
        <span class="badge-status">${badge.text} · #${t.id}</span>
        <small>${t.created_at || ""}</small>
      </div>
      <div><strong>User:</strong> <code>${t.user_id}</code></div>
      <div><strong>Thread:</strong> <code>${t.thread_id}</code></div>
      <div><strong>Claimed by:</strong> <code>${t.claimed_by || "-"}</code></div>
      <div><strong>Rating:</strong> <code>${t.rating || "-"}</code></div>
    `;
    root.appendChild(div);
  }
}

let ticketCache = [];

function formatDate(value) {
  if (!value) return "–";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString("de-DE");
}

async function loadGlobalSummary() {
  const data = await api("/api/global/summary");
  const tickets = data.tickets || {};
  $("globalTickets").textContent = tickets.total ?? 0;
  $("globalGiveaways").textContent = data.giveaways ?? 0;
  $("globalPolls").textContent = data.polls ?? 0;
  $("globalApps").textContent = data.applications ?? 0;
  $("globalBirthdays").textContent = data.birthdays ?? 0;
}

async function loadGuildSummary() {
  const gid = requireGuild();
  const data = await api(`/api/guilds/${gid}/summary`);
  const tickets = data.tickets || {};
  $("guildTicketsOpen").textContent = tickets.open ?? 0;
  $("guildTicketsTotal").textContent = tickets.total ?? 0;
  $("guildGiveaways").textContent = data.giveaways ?? 0;
  $("guildPolls").textContent = data.polls ?? 0;
  $("guildApps").textContent = data.applications ?? 0;
}

async function loadTickets() {
  const gid = requireGuild();
  ticketCache = await api(`/api/guilds/${gid}/tickets?limit=200`);
  renderTickets(ticketCache);
}

async function loadGuildOverrides() {
  const gid = requireGuild();
  const data = await api(`/api/guilds/${gid}/overrides`);
  $("settings").value = JSON.stringify(data, null, 2);
}

async function applyGuildOverrides() {
  const gid = requireGuild();
  const raw = $("settings").value.trim();
  const data = raw ? JSON.parse(raw) : {};
  await api(`/api/guilds/${gid}/overrides`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

async function loadApplications() {
  const gid = requireGuild();
  const data = await api(`/api/guilds/${gid}/applications`);
  $("applications").value = JSON.stringify(data, null, 2);
}

async function applyApplications() {
  const gid = requireGuild();
  const raw = $("applications").value.trim();
  const data = raw ? JSON.parse(raw) : {};
  await api(`/api/guilds/${gid}/applications`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

async function loadApplicationsList() {
  const gid = requireGuild();
  const list = await api(`/api/guilds/${gid}/applications/list?limit=100`);
  const root = $("applicationsList");
  root.innerHTML = "";
  if (!list.length) {
    root.innerHTML = '<div class="list-item">Keine Bewerbungen.</div>';
    return;
  }
  for (const row of list) {
    const div = document.createElement("div");
    div.className = "list-item";
    div.innerHTML = `<strong>#${row.id}</strong> · <code>${row.user_id}</code> · <code>${row.thread_id}</code><br><small>${row.status} · ${row.created_at}</small>`;
    root.appendChild(div);
  }
}

async function loadLogs() {
  const list = await api("/api/logs?limit=200");
  const root = $("logs");
  root.innerHTML = "";
  if (!list.length) {
    root.innerHTML = '<div class="list-item">Keine Logs.</div>';
    return;
  }
  for (const row of list) {
    const div = document.createElement("div");
    div.className = "list-item";
    div.innerHTML = `<strong>${row.event}</strong> · <small>${row.created_at}</small><br><code>${row.payload}</code>`;
    root.appendChild(div);
  }
}

let logSocket = null;
function connectLogs() {
  if (logSocket && logSocket.readyState === 1) return;
  const status = $("logsLiveStatus");
  status.textContent = "Verbinde…";
  logSocket = new WebSocket(`ws://${location.host}/ws/logs`);
  logSocket.onopen = () => { status.textContent = "Verbunden"; };
  logSocket.onclose = () => { status.textContent = "Getrennt"; };
  logSocket.onerror = () => { status.textContent = "Fehler"; };
  logSocket.onmessage = (ev) => {
    try {
      const row = JSON.parse(ev.data);
      const root = $("logs");
      const div = document.createElement("div");
      div.className = "list-item";
      div.innerHTML = `<strong>${row.event}</strong> · <small>${row.created_at}</small><br><code>${row.payload}</code>`;
      root.prepend(div);
    } catch (e) {
      /* ignore */
    }
  };
}

async function searchUsers() {
  const gid = requireGuild();
  const q = $("userSearchInput").value.trim();
  if (!q) return;
  const list = await api(`/api/guilds/${gid}/users/search?query=${encodeURIComponent(q)}`);
  const root = $("userSearchResults");
  root.innerHTML = "";
  if (!list.length) {
    root.innerHTML = '<div class="list-item">Keine Treffer.</div>';
    return;
  }
  for (const row of list) {
    const div = document.createElement("div");
    div.className = "list-item";
    div.innerHTML = `<strong>${row.display_name}</strong> · <code>${row.id}</code>`;
    root.appendChild(div);
  }
}

async function loadLiveUsers() {
  const gid = requireGuild();
  const list = await api(`/api/guilds/${gid}/users/live?limit=50`);
  const root = $("userLive");
  root.innerHTML = "";
  if (!list.length) {
    root.innerHTML = '<div class="list-item">Keine aktiven User.</div>';
    return;
  }
  for (const row of list) {
    const div = document.createElement("div");
    div.className = "list-item";
    div.innerHTML = `<strong>${row.display_name}</strong> · <code>${row.id}</code><br><small>${row.status}</small>`;
    root.appendChild(div);
  }
}

async function loadBirthdays() {
  const data = await api("/api/global/birthdays?limit=50&offset=0");
  const root = $("birthdays");
  root.innerHTML = "";
  if (!data.items.length) {
    root.innerHTML = '<div class="list-item">Keine Geburtstage.</div>';
    return;
  }
  for (const row of data.items) {
    const div = document.createElement("div");
    div.className = "list-item";
    div.innerHTML = `<strong><code>${row.user_id}</code></strong> · ${row.day}.${row.month}.${row.year}`;
    root.appendChild(div);
  }
}

async function loadBirthdaySummary() {
  const gid = requireGuild();
  const data = await api(`/api/guilds/${gid}/birthdays/summary`);

  $("birthdayTodayCount").textContent = data.total_today ?? 0;
  $("birthdayNextCount").textContent = data.total_next ?? 0;
  $("birthdayBoosterCount").textContent = data.total_boosters ?? 0;
  $("birthdayTotalCount").textContent = data.total_birthdays ?? 0;

  $("birthdayTodayBadge").textContent = data.date ? formatDate(data.date) : (data.total_today ?? 0);
  $("birthdayNextBadge").textContent = data.total_next ?? 0;
  $("birthdayBoosterBadge").textContent = data.total_boosters ?? 0;

  const todayRoot = $("birthdaysToday");
  todayRoot.innerHTML = "";
  const today = data.today || [];
  if (!today.length) {
    todayRoot.innerHTML = '<div class="list-item">Heute hat niemand Geburtstag.</div>';
  } else {
    for (const row of today) {
      const div = document.createElement("div");
      div.className = "list-item";
      const ageLine = row.age ? `wird ${row.age}` : "—";
      div.innerHTML = `<strong>${row.display_name}</strong> · <code>${row.user_id}</code><br><small>${ageLine}</small>`;
      todayRoot.appendChild(div);
    }
  }

  const nextRoot = $("birthdaysNext");
  nextRoot.innerHTML = "";
  const next = data.next || [];
  if (!next.length) {
    nextRoot.innerHTML = '<div class="list-item">Keine anstehenden Termine.</div>';
  } else {
    for (const row of next) {
      const div = document.createElement("div");
      div.className = "list-item";
      const dateLine = `${row.day}.${row.month} · in ${row.days_until} Tagen`;
      const turns = row.turns ? ` · wird ${row.turns}` : "";
      div.innerHTML = `<strong>${row.display_name}</strong> · <code>${row.user_id}</code><br><small>${dateLine}${turns}</small>`;
      nextRoot.appendChild(div);
    }
  }

  const boostersRoot = $("boosters");
  boostersRoot.innerHTML = "";
  const boosters = data.boosters || [];
  if (!boosters.length) {
    boostersRoot.innerHTML = '<div class="list-item">Keine Booster gespeichert.</div>';
  } else {
    for (const row of boosters) {
      const div = document.createElement("div");
      div.className = "list-item";
      const since = formatDate(row.premium_since);
      div.innerHTML = `<strong>${row.display_name}</strong> · <code>${row.user_id}</code><br><small>seit ${since}</small>`;
      boostersRoot.appendChild(div);
    }
  }
}

async function postJson(path, payload) {
  return api(path, { method: "POST", body: JSON.stringify(payload) });
}

async function refreshGuildData() {
  await Promise.all([
    loadGuildSummary(),
    loadTickets(),
    loadApplications(),
    loadApplicationsList(),
    loadBirthdaySummary(),
  ]);
}

async function init() {
  try {
    const me = await api("/api/me");
    state.user = me.user;
    state.guilds = me.guilds || [];
    setAuthState(true);
    $("userName").textContent = me.user.username;
    if (me.user.avatar) {
      $("userAvatar").src = `https://cdn.discordapp.com/avatars/${me.user.id}/${me.user.avatar}.png`;
    }
    renderGuilds();
    const remembered = Number(localStorage.getItem("starry_guild"));
    if (remembered && state.guilds.find((g) => g.id === remembered)) {
      selectGuild(remembered);
    }
    await loadGlobalSummary();
  } catch (e) {
    setAuthState(false);
  }
}

// Navigation
Array.from(document.querySelectorAll(".nav-btn")).forEach((btn) => {
  btn.addEventListener("click", () => {
    setView(btn.dataset.view);
    if (btn.dataset.view === "birthdays") {
      loadBirthdays().catch((e) => toast(e.message));
      loadBirthdaySummary().catch(() => null);
    }
  });
});

// Auth
$("loginBtn").onclick = () => (window.location.href = "/login");
$("loginHero").onclick = () => (window.location.href = "/login");
$("logoutBtn").onclick = () => (window.location.href = "/logout");

// Overview
$("refreshGlobal").onclick = () => loadGlobalSummary().then(() => toast("Global aktualisiert"));
$("refreshGuild").onclick = () => loadGuildSummary().then(() => toast("Guild aktualisiert"));

// Tickets
$("ticketsReload").onclick = () => loadTickets().then(() => toast("Tickets geladen")).catch((e) => toast(e.message));
$("ticketSearch").oninput = () => renderTickets(ticketCache);
$("ticketActionBtn").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/tickets/action`, {
    thread_id: $("ticketThreadId").value.trim(),
    actor_id: $("ticketActorId").value.trim(),
    user_id: $("ticketUserId").value.trim(),
    action: $("ticketAction").value,
    reason: $("ticketReason").value.trim(),
  }).then(() => toast("Ticket Aktion ausgeführt")).catch((e) => toast(e.message));
};

// Messaging
$("sendMessage").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/discord/message`, {
    channel_id: $("msgChannelId").value.trim(),
    content: $("msgContent").value.trim(),
  }).then(() => toast("Nachricht gesendet")).catch((e) => toast(e.message));
};

$("sendEmbed").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/discord/embed`, {
    channel_id: $("embedChannelId").value.trim(),
    title: $("embedTitle").value.trim(),
    description: $("embedDesc").value.trim(),
    color: $("embedColor").value.trim(),
    footer: $("embedFooter").value.trim(),
    thumbnail: $("embedThumbnail").value.trim(),
    image: $("embedImage").value.trim(),
    fields: parseFields($("embedFields").value),
  }).then(() => toast("Embed gesendet")).catch((e) => toast(e.message));
};

// Moderation
$("timeoutBtn").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/moderation/timeout`, {
    user_id: $("timeoutUserId").value.trim(),
    moderator_id: $("timeoutModeratorId").value.trim(),
    minutes: $("timeoutMinutes").value.trim(),
    reason: $("timeoutReason").value.trim(),
  }).then(() => toast("Timeout gesetzt")).catch((e) => toast(e.message));
};

$("kickBtn").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/moderation/kick`, {
    user_id: $("kickUserId").value.trim(),
    moderator_id: $("kickModeratorId").value.trim(),
    reason: $("kickReason").value.trim(),
  }).then(() => toast("User gekickt")).catch((e) => toast(e.message));
};

$("banBtn").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/moderation/ban`, {
    user_id: $("banUserId").value.trim(),
    moderator_id: $("banModeratorId").value.trim(),
    delete_days: $("banDays").value.trim(),
    reason: $("banReason").value.trim(),
  }).then(() => toast("User gebannt")).catch((e) => toast(e.message));
};

$("purgeBtn").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/moderation/purge`, {
    channel_id: $("purgeChannelId").value.trim(),
    moderator_id: $("purgeModeratorId").value.trim(),
    amount: $("purgeAmount").value.trim(),
    user_id: $("purgeUserId").value.trim(),
  }).then((res) => toast("Purge: " + res.deleted)).catch((e) => toast(e.message));
};

// Roles
$("roleAddBtn").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/roles/add`, {
    user_id: $("roleAddUserId").value.trim(),
    role_id: $("roleAddRoleId").value.trim(),
  }).then(() => toast("Rolle hinzugefügt")).catch((e) => toast(e.message));
};

$("roleRemoveBtn").onclick = () => {
  const gid = requireGuild();
  postJson(`/api/guilds/${gid}/roles/remove`, {
    user_id: $("roleRemoveUserId").value.trim(),
    role_id: $("roleRemoveRoleId").value.trim(),
  }).then(() => toast("Rolle entfernt")).catch((e) => toast(e.message));
};

// Users
$("userSearchBtn").onclick = () => searchUsers().catch((e) => toast(e.message));
$("userLiveReload").onclick = () => loadLiveUsers().then(() => toast("Live User geladen")).catch((e) => toast(e.message));

// Applications
$("appsReload").onclick = () => loadApplications().then(() => toast("Applications geladen")).catch((e) => toast(e.message));
$("appsApply").onclick = () => applyApplications().then(() => toast("Applications gespeichert")).catch((e) => toast(e.message));
$("appsListReload").onclick = () => loadApplicationsList().then(() => toast("Bewerbungen aktualisiert")).catch((e) => toast(e.message));

// Logs
$("logsReload").onclick = () => loadLogs().then(() => toast("Logs geladen")).catch((e) => toast(e.message));
$("logsLive").onclick = () => connectLogs();

// Settings
$("reload").onclick = () => loadGuildOverrides().then(() => toast("Overrides geladen")).catch((e) => toast(e.message));
$("apply").onclick = () => applyGuildOverrides().then(() => toast("Gespeichert"))
  .catch((e) => toast(e.message));
$("prettify").onclick = () => {
  try {
    const obj = JSON.parse($("settings").value);
    $("settings").value = JSON.stringify(obj, null, 2);
    toast("Formatiert");
  } catch (e) {
    toast("JSON ungültig");
  }
};

// Birthdays
$("birthdaysReload").onclick = () => Promise.all([
  loadBirthdays(),
  loadBirthdaySummary().catch(() => null),
]).then(() => toast("Birthdays geladen")).catch((e) => toast(e.message));

init();
