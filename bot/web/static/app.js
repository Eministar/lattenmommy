const $ = (id) => document.getElementById(id);

function getToken() {
  return localStorage.getItem("starry_token") || "";
}
function setToken(t) {
  localStorage.setItem("starry_token", t);
}

async function api(path, opts = {}) {
  const token = getToken();
  const headers = Object.assign({}, opts.headers || {}, {
    "Authorization": "Bearer " + token
  });
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(res.status + " " + txt);
  }
  return res.json();
}

async function loadSettings() {
  const s = await api("/api/settings");
  $("settings").value = JSON.stringify(s, null, 2);
}

async function applySettings() {
  const raw = $("settings").value.trim();
  const data = JSON.parse(raw);
  await api("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}

function badge(status) {
  if (status === "closed") return "🔴 geschlossen";
  if (status === "claimed") return "🟠 geclaimed";
  return "🟢 offen";
}

async function loadTickets() {
  const list = await api("/api/tickets?limit=200");
  const el = $("tickets");
  el.innerHTML = "";
  for (const t of list) {
    const div = document.createElement("div");
    div.className = "ticket";
    div.innerHTML = `
      <div class="badge">${badge(t.status)} • #${t.id}</div>
      <div class="line">User: ${t.user_id}</div>
      <div class="line">Thread: ${t.thread_id}</div>
      <div class="line">Claimed by: ${t.claimed_by || "-"}</div>
      <div class="line">Rating: ${t.rating || "-"}</div>
    `;
    el.appendChild(div);
  }
}

$("token").value = getToken();
$("saveToken").onclick = () => setToken($("token").value.trim());
$("reload").onclick = () => loadSettings().catch(e => alert(e.message));
$("apply").onclick = () => applySettings().then(() => alert("Gespeichert. Bot übernimmt das automatisch.")).catch(e => alert(e.message));
$("ticketsReload").onclick = () => loadTickets().catch(e => alert(e.message));

loadSettings().catch(() => {});
loadTickets().catch(() => {});
