const display = document.querySelector("#display");
const apiStatus = document.querySelector("#api-status");
const hubDialog = document.querySelector("#hub-dialog");
const hubList = document.querySelector("#hub-list");
const hubDialogMeta = document.querySelector("#hub-dialog-meta");
const scoreInput = document.querySelector("#score");
const setScoreButton = document.querySelector("#set-score");
const scoreMinusButton = document.querySelector("#score-minus");
const scorePlusButton = document.querySelector("#score-plus");
const fullPullButton = document.querySelector("#full-pull");
const resetButton = document.querySelector("#reset");
const setWeightButton = document.querySelector("#set-weight");
const weightPercentInput = document.querySelector("#weight-percent");
const sledCommandEl = document.querySelector("#sled-command");
const scoreboardCommandEl = document.querySelector("#scoreboard-command");
const historyForm = document.querySelector("#history-form");
const tractorInput = document.querySelector("#tractor");
const resultInput = document.querySelector("#result");
const clearHistoryButton = document.querySelector("#clear-history");
const historyBody = document.querySelector("#history-body");

let lastHubSnapshot = null;

function setOnlineStatus(isOnline, hubSnapshot) {
  apiStatus.classList.toggle("offline", !isOnline);
  if (!isOnline) {
    apiStatus.textContent = "Server offline";
    return;
  }
  if (hubSnapshot && Array.isArray(hubSnapshot.hubs)) {
    const total = hubSnapshot.hubs.length;
    const connected = hubSnapshot.hubs.filter((h) => h.connected).length;
    if (total === 0) {
      apiStatus.textContent = hubSnapshot.stale ? "Bridge offline" : "Ingen hubs";
      apiStatus.classList.toggle("offline", hubSnapshot.stale || total === 0);
      return;
    }
    apiStatus.textContent = `Hubs ${connected}/${total}`;
    apiStatus.classList.toggle("offline", hubSnapshot.stale || connected < total);
    return;
  }
  apiStatus.textContent = "Server online";
}

function renderHubDialog() {
  if (!hubList) return;
  hubList.innerHTML = "";
  if (!lastHubSnapshot) {
    hubDialogMeta.textContent = "Ingen status fra bridge endnu.";
    return;
  }
  const { hubs = [], age_seconds, stale } = lastHubSnapshot;
  const ageText =
    age_seconds == null ? "aldrig" : `${Math.round(age_seconds)}s siden`;
  hubDialogMeta.textContent = stale
    ? `Bridge offline (sidste opdatering: ${ageText})`
    : `Opdateret ${ageText}`;
  if (!hubs.length) {
    const li = document.createElement("li");
    li.className = "hub-row empty";
    li.textContent = "Ingen hubs registreret.";
    hubList.appendChild(li);
    return;
  }
  for (const h of hubs) {
    const li = document.createElement("li");
    li.className = "hub-row";
    const status = h.connected ? "online" : "offline";
    li.innerHTML = `
      <div class="hub-row-main">
        <span class="hub-label">${h.label}</span>
        <span class="hub-name">${h.name || ""}</span>
      </div>
      <div class="hub-row-side">
        <span class="hub-badge ${status}">${h.connected ? "Forbundet" : "Afbrudt"}</span>
        <button type="button" class="btn btn-reconnect" data-action="reconnect" data-label="${h.label}">Forbind</button>
        <button type="button" class="btn btn-reboot" data-action="reboot" data-label="${h.label}">Reboot</button>
        <button type="button" class="btn btn-release" data-action="release" data-label="${h.label}" title="Frigør hubben så en anden enhed (fx telefon) kan forbinde">Slip</button>
      </div>
      ${h.error ? `<div class="hub-error">${h.error}</div>` : ""}
    `;
    hubList.appendChild(li);
  }
}

async function refreshHubStatus() {
  try {
    lastHubSnapshot = await getJson("/api/bridge-status");
  } catch (e) {
    lastHubSnapshot = null;
  }
  setOnlineStatus(true, lastHubSnapshot);
  if (hubDialog && hubDialog.open) {
    renderHubDialog();
  }
}

function formatTimestamp(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return value;
  }
  return d.toLocaleString("da-DK", {
    hour12: false,
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderDisplay(scoreboard) {
  if (scoreboard.full_pull) {
    display.textContent = "FULL PULL!!!";
  } else {
    display.textContent = String(scoreboard.score).padStart(3, "0");
  }

  // Don't overwrite manual typing every second while input is focused.
  if (document.activeElement !== scoreInput) {
    scoreInput.value = scoreboard.score;
  }
}

function renderLastCommand(target, command) {
  if (!command) {
    target.textContent = "Ingen kommando endnu";
    return;
  }
  target.textContent = `${formatTimestamp(command.timestamp)} - ${JSON.stringify(command.payload)}`;
}

function renderHistory(rows) {
  historyBody.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="3" class="empty">Ingen historik endnu</td>';
    historyBody.appendChild(tr);
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatTimestamp(row.timestamp)}</td>
      <td>${row.tractor}</td>
      <td>${Number(row.result_m).toFixed(1)}</td>
    `;
    historyBody.appendChild(tr);
  }
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function poll() {
  try {
    const [live, history] = await Promise.all([getJson("/api/live"), getJson("/api/history")]);
    renderDisplay(live.scoreboard);
    renderLastCommand(sledCommandEl, live.last_sled_command);
    renderLastCommand(scoreboardCommandEl, live.last_scoreboard_command);
    renderHistory(history);
    await refreshHubStatus();
  } catch (error) {
    setOnlineStatus(false);
  }
}

setScoreButton.addEventListener("click", async () => {
  const score = Number(scoreInput.value || 0);
  await postJson("/api/remote/scoreboard", { action: "set_score", value: score });
  await poll();
});

scorePlusButton.addEventListener("click", async () => {
  const score = Math.min(999, Number(scoreInput.value || 0) + 1);
  await postJson("/api/remote/scoreboard", { action: "set_score", value: score });
  await poll();
});

scoreMinusButton.addEventListener("click", async () => {
  const score = Math.max(0, Number(scoreInput.value || 0) - 1);
  await postJson("/api/remote/scoreboard", { action: "set_score", value: score });
  await poll();
});

fullPullButton.addEventListener("click", async () => {
  await postJson("/api/remote/scoreboard", { action: "full_pull" });
  await poll();
});

resetButton.addEventListener("click", async () => {
  await postJson("/api/remote/scoreboard", { action: "reset" });
  await poll();
});

document.querySelectorAll(".sled-action").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const action = btn.dataset.sledAction;
    await postJson("/api/remote/sled", { action });
    await poll();
  });
});

setWeightButton.addEventListener("click", async () => {
  const value = Number(weightPercentInput.value || 0);
  await postJson("/api/remote/sled", { action: "set_weight_percent", value });
  await poll();
});

historyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await postJson("/api/history", {
    tractor: tractorInput.value.trim(),
    result_m: Number(resultInput.value || 0),
  });
  tractorInput.value = "";
  resultInput.value = "";
  await poll();
});

clearHistoryButton.addEventListener("click", async () => {
  await fetch("/api/history", { method: "DELETE" });
  await poll();
});

if (apiStatus && hubDialog) {
  apiStatus.addEventListener("click", async () => {
    await refreshHubStatus();
    renderHubDialog();
    if (typeof hubDialog.showModal === "function") {
      hubDialog.showModal();
    } else {
      hubDialog.setAttribute("open", "");
    }
  });
}

if (hubList) {
  hubList.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const action = target.dataset.action;
    const label = target.dataset.label;
    if (!action || !label) return;
    target.disabled = true;
    const original = target.textContent;
    target.textContent = "Sender...";
    try {
      await postJson(`/api/bridge-control/${action}/${encodeURIComponent(label)}`);
      target.textContent = "Anmodet";
    } catch (e) {
      target.textContent = "Fejl";
      target.disabled = false;
    }
    setTimeout(() => {
      target.textContent = original;
      target.disabled = false;
      refreshHubStatus();
    }, 2000);
  });
}

const rebootAllButton = document.querySelector("#reboot-all");
if (rebootAllButton) {
  rebootAllButton.addEventListener("click", async (event) => {
    event.preventDefault();
    rebootAllButton.disabled = true;
    const original = rebootAllButton.textContent;
    rebootAllButton.textContent = "Sender...";
    try {
      await postJson("/api/bridge-control/reboot/all");
      rebootAllButton.textContent = "Anmodet";
    } catch (e) {
      rebootAllButton.textContent = "Fejl";
    }
    setTimeout(() => {
      rebootAllButton.textContent = original;
      rebootAllButton.disabled = false;
      refreshHubStatus();
    }, 2000);
  });
}

poll();
setInterval(poll, 1000);

