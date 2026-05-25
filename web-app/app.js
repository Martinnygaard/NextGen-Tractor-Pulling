// Pybricks Profile BLE UUIDs.
const PYBRICKS_SERVICE = "c5f50001-8280-46da-89f4-6d8051e4aeef";
const PYBRICKS_COMMAND_EVENT_CHAR = "c5f50002-8280-46da-89f4-6d8051e4aeef";
const PYBRICKS_HUB_CAPS_CHAR = "c5f50003-8280-46da-89f4-6d8051e4aeef";

const CMD_STOP_USER_PROGRAM = 0x00;
const CMD_START_USER_PROGRAM = 0x01;
const CMD_WRITE_USER_PROGRAM_META = 0x03;
const CMD_WRITE_USER_RAM = 0x04;
const CMD_WRITE_STDIN = 0x06;
const EVT_STATUS_REPORT = 0x00;
const EVT_WRITE_STDOUT = 0x01;

// Pybricks status flag bits (uint32 bitfield in EVT_STATUS_REPORT).
const STATUS_USER_PROGRAM_RUNNING = 1 << 6;
const STATUS_BLE_ADVERTISING = 1 << 3;
const STATUS_BATTERY_LOW = 1 << 0;

const SLED_ACTIONS = {
    start_pull: 1,
    stop_pull: 2,
    home_weight: 3,
    set_signal_red: 4,
    set_signal_green: 5,
    set_weight_percent: 6,
    reset_distance: 7,
    clear_signal: 8,
    set_signal_green_blink: 9,
    set_ramp_end_m: 10,
    set_full_rotations: 11,
};

const ui = {
    log: document.getElementById("log"),
    distance: document.getElementById("distance"),
    lastAck: document.getElementById("last-ack"),
    lastSeq: document.getElementById("last-seq"),

    hubsBtn: document.getElementById("btn-hubs"),
    manualBtn: document.getElementById("btn-manual"),
    settingsBtn: document.getElementById("btn-settings"),
    hubDialog: document.getElementById("hub-dialog"),
    manualDialog: document.getElementById("manual-dialog"),
    settingsDialog: document.getElementById("settings-dialog"),

    // Master
    connect: document.getElementById("btn-connect"),
    disconnect: document.getElementById("btn-disconnect"),
    startProgram: document.getElementById("btn-start-program"),
    stopProgram: document.getElementById("btn-stop-program"),
    status: document.getElementById("status"),

    // Sled
    sledConnect: document.getElementById("btn-sled-connect"),
    sledDisconnect: document.getElementById("btn-sled-disconnect"),
    sledStart: document.getElementById("btn-sled-start"),
    sledStop: document.getElementById("btn-sled-stop"),
    sledPushCfg: document.getElementById("btn-push-config"),
    sledPushCfg2: document.getElementById("btn-push-config-2"),
    sledStatus: document.getElementById("sled-status"),

    // Displays
    display1Connect: document.getElementById("btn-display1-connect"),
    display1Disconnect: document.getElementById("btn-display1-disconnect"),
    display1Start: document.getElementById("btn-display1-start"),
    display1Stop: document.getElementById("btn-display1-stop"),
    display1Status: document.getElementById("display1-status"),
    display2Connect: document.getElementById("btn-display2-connect"),
    display2Disconnect: document.getElementById("btn-display2-disconnect"),
    display2Start: document.getElementById("btn-display2-start"),
    display2Stop: document.getElementById("btn-display2-stop"),
    display2Status: document.getElementById("display2-status"),
    display3Connect: document.getElementById("btn-display3-connect"),
    display3Disconnect: document.getElementById("btn-display3-disconnect"),
    display3Start: document.getElementById("btn-display3-start"),
    display3Stop: document.getElementById("btn-display3-stop"),
    display3Status: document.getElementById("display3-status"),

    // Flash (program upload) buttons
    flashMaster: document.getElementById("btn-flash-master"),
    flashSled: document.getElementById("btn-flash-sled"),
    flashDisplay1: document.getElementById("btn-flash-display1"),
    flashDisplay2: document.getElementById("btn-flash-display2"),
    flashDisplay3: document.getElementById("btn-flash-display3"),

    // Score + sled
    sendScore: document.getElementById("btn-send-score"),
    fullPull: document.getElementById("btn-full-pull"),
    score: document.getElementById("score"),
    sledButtons: document.querySelectorAll(".sled-action"),

    // Config
    cfgRamp: document.getElementById("cfg-ramp"),
    cfgRampVal: document.getElementById("cfg-ramp-val"),
    cfgRot: document.getElementById("cfg-rot"),
    cfgRotVal: document.getElementById("cfg-rot-val"),
    cfgPlates: document.getElementById("cfg-plates"),
    cfgPlatesVal: document.getElementById("cfg-plates-val"),
    cfgWeightDisplay: document.getElementById("cfg-weight-display"),
    btnPlatesPlus: document.getElementById("btn-plates-plus"),
    btnPlatesMinus: document.getElementById("btn-plates-minus"),

    // Scoreboard
    entryName: document.getElementById("entry-name"),
    btnAddEntry: document.getElementById("btn-add-entry"),
    entryWeightPreview: document.getElementById("entry-weight-preview"),
    scoreboardBody: document.getElementById("scoreboard-body"),
    knownNames: document.getElementById("known-names"),
    editDialog: document.getElementById("edit-dialog"),
    editTime: document.getElementById("edit-time"),
    editName: document.getElementById("edit-name"),
    editWeight: document.getElementById("edit-weight"),
    editDistance: document.getElementById("edit-distance"),
    btnEditSave: document.getElementById("btn-edit-save"),
    btnEditDelete: document.getElementById("btn-edit-delete"),
};

let cmdSeq = 0;

function log(line) {
    const ts = new Date().toLocaleTimeString("da-DK", { hour12: false });
    ui.log.textContent += `[${ts}] ${line}\n`;
    ui.log.scrollTop = ui.log.scrollHeight;
}

function setStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text;
    el.dataset.kind = kind || "";
}

function setDistance(meters) {
    if (!ui.distance) return;
    ui.distance.textContent = meters.toFixed(1) + " m";
}

// ---------------- Hub abstraction ----------------

class HubConnection {
    constructor(label, namePrefix, onLine) {
        this.label = label;
        this.namePrefix = namePrefix;
        this.onLine = onLine;
        this.device = null;
        this.server = null;
        this.service = null;
        this.commandChar = null;
        this.maxWriteSize = 20; // ATT default; may be raised after connect
        this.stdoutBuffer = "";
        this.statusFlags = 0;
        this.hasStatus = false;
        this.flashing = false;
        this.flashProgress = 0;
        this.onStateChange = () => { };
    }

    isConnected() {
        return !!this.commandChar;
    }

    isProgramRunning() {
        return !!(this.statusFlags & STATUS_USER_PROGRAM_RUNNING);
    }

    async connect() {
        if (!("bluetooth" in navigator)) {
            throw new Error("Web Bluetooth ikke tilgængelig");
        }
        this.device = await navigator.bluetooth.requestDevice({
            filters: [{ namePrefix: this.namePrefix }],
            optionalServices: [PYBRICKS_SERVICE],
        });
        this.device.addEventListener("gattserverdisconnected", () => {
            log(`${this.label}: afbrudt`);
            this.commandChar = null;
            this.service = null;
            this.server = null;
            this.statusFlags = 0;
            this.hasStatus = false;
            this.flashing = false;
            this.onStateChange();
        });
        this.server = await this.device.gatt.connect();
        const service = await this.server.getPrimaryService(PYBRICKS_SERVICE);
        this.service = service;
        this.commandChar = await service.getCharacteristic(PYBRICKS_COMMAND_EVENT_CHAR);
        await this.commandChar.startNotifications();
        this.commandChar.addEventListener("characteristicvaluechanged", (e) => this._onEvent(e));

        // Discover max characteristic write size from the Hub Capabilities
        // characteristic so we can use larger chunks while uploading programs.
        try {
            const capsChar = await service.getCharacteristic(PYBRICKS_HUB_CAPS_CHAR);
            const caps = await capsChar.readValue();
            if (caps.byteLength >= 2) {
                const maxWrite = caps.getUint16(0, true);
                if (maxWrite >= 20 && maxWrite <= 512) {
                    this.maxWriteSize = maxWrite;
                    log(`${this.label}: max BLE write = ${maxWrite} bytes`);
                }
            }
        } catch (e) {
            // Older firmware may not expose the capability characteristic.
        }

        log(`${this.label}: forbundet til ${this.device.name}`);
        this.onStateChange();
    }

    async disconnect() {
        if (this.device && this.device.gatt && this.device.gatt.connected) {
            this.device.gatt.disconnect();
        }
    }

    _onEvent(event) {
        const dv = event.target.value;
        if (!dv || dv.byteLength < 1) return;
        const data = new Uint8Array(dv.buffer, dv.byteOffset, dv.byteLength);
        const evtId = data[0];
        if (evtId === EVT_STATUS_REPORT) {
            if (data.byteLength >= 5) {
                // uint32 little-endian status bitfield.
                const flags = data[1] | (data[2] << 8) | (data[3] << 16) | (data[4] << 24);
                const prev = this.statusFlags;
                this.statusFlags = flags >>> 0;
                this.hasStatus = true;
                if (((prev ^ flags) & STATUS_USER_PROGRAM_RUNNING) !== 0) {
                    log(`${this.label}: program ${this.isProgramRunning() ? "kører" : "stoppet"}`);
                }
                this.onStateChange();
            }
            return;
        }
        if (evtId === EVT_WRITE_STDOUT) {
            const text = new TextDecoder().decode(data.subarray(1));
            this.stdoutBuffer += text;
            let idx;
            while ((idx = this.stdoutBuffer.indexOf("\n")) >= 0) {
                const line = this.stdoutBuffer.slice(0, idx).replace(/\r$/, "");
                this.stdoutBuffer = this.stdoutBuffer.slice(idx + 1);
                if (!line.length) continue;
                if (this.onLine) this.onLine(line);
                log(`${this.label}: ${line}`);
            }
        }
    }

    async writeStdin(text) {
        if (!this.commandChar) throw new Error(`${this.label} ikke forbundet`);
        const bytes = new TextEncoder().encode(text);
        const CHUNK = 18;
        for (let off = 0; off < bytes.length; off += CHUNK) {
            const slice = bytes.subarray(off, off + CHUNK);
            const frame = new Uint8Array(1 + slice.length);
            frame[0] = CMD_WRITE_STDIN;
            frame.set(slice, 1);
            await this.commandChar.writeValueWithResponse(frame);
        }
    }

    async startProgram() {
        if (!this.commandChar) return;
        await this.commandChar.writeValueWithResponse(new Uint8Array([CMD_START_USER_PROGRAM, 0]));
        log(`${this.label}: START_USER_PROGRAM`);
    }

    async stopProgram() {
        if (!this.commandChar) return;
        await this.commandChar.writeValueWithResponse(new Uint8Array([CMD_STOP_USER_PROGRAM]));
        log(`${this.label}: STOP_USER_PROGRAM`);
    }

    async flashProgram(mpyUrl) {
        if (!this.commandChar) throw new Error("Ikke forbundet");
        if (this.flashing) throw new Error("Allerede ved at flashe");

        // Fetch the .mpy bundle from the deployed PWA (cache-busted).
        const url = mpyUrl + (mpyUrl.includes("?") ? "&" : "?") + "ts=" + Date.now();
        const resp = await fetch(url, { cache: "no-store" });
        if (!resp.ok) throw new Error(`Hentning fejlede: HTTP ${resp.status}`);
        const data = new Uint8Array(await resp.arrayBuffer());
        if (data.length === 0) throw new Error("Tomt program");

        // Stop any running program first (best-effort).
        try { await this.stopProgram(); } catch (_) { /* ignore */ }

        this.flashing = true;
        this.flashProgress = 0;
        this.onStateChange();

        try {
            // Each WRITE_USER_RAM frame is: 1 byte cmd + 4 byte offset + payload.
            const overhead = 1 + 4;
            const chunkSize = Math.max(16, this.maxWriteSize - overhead);

            // 1. WRITE_USER_PROGRAM_META with total size.
            {
                const buf = new Uint8Array(5);
                buf[0] = CMD_WRITE_USER_PROGRAM_META;
                new DataView(buf.buffer).setUint32(1, data.length, true);
                await this.commandChar.writeValueWithResponse(buf);
            }

            // 2. WRITE_USER_RAM in chunks.
            for (let off = 0; off < data.length; off += chunkSize) {
                const end = Math.min(off + chunkSize, data.length);
                const slice = data.subarray(off, end);
                const buf = new Uint8Array(overhead + slice.length);
                buf[0] = CMD_WRITE_USER_RAM;
                new DataView(buf.buffer).setUint32(1, off, true);
                buf.set(slice, overhead);
                await this.commandChar.writeValueWithResponse(buf);
                this.flashProgress = end / data.length;
                this.onStateChange();
            }

            log(`${this.label}: program flashet (${data.length} bytes)`);
        } finally {
            this.flashing = false;
            this.flashProgress = 0;
            this.onStateChange();
        }
    }
}

// ---------------- Hub instances ----------------

const master = new HubConnection("master", "Puller Master", (line) => {
    if (line.startsWith("D ")) {
        const v = parseInt(line.slice(2).trim(), 10);
        if (!Number.isNaN(v)) setDistance(v / 10);
        return;
    }
    if (line.startsWith("A ")) {
        const v = parseInt(line.slice(2).trim(), 10);
        if (!Number.isNaN(v) && ui.lastAck) ui.lastAck.textContent = String(v);
        return;
    }
});

const sled = new HubConnection("sled", "Puller Sled", null);

const displays = [
    new HubConnection("display1", "Puller Score 1", null),
    new HubConnection("display2", "Puller Score 2", null),
    new HubConnection("display3", "Puller Score 3", null),
];
const [display1, display2, display3] = displays;

// .mpy program bundles produced by tools/build_programs.py in CI and shipped
// alongside the PWA. Each entry maps a HubConnection label to the bundle URL.
const PROGRAM_URLS = {
    master: "programs/master.mpy",
    sled: "programs/sled.mpy",
    display1: "programs/display1.mpy",
    display2: "programs/display2.mpy",
    display3: "programs/display3.mpy",
};

async function flashHub(hub) {
    const url = PROGRAM_URLS[hub.label];
    if (!url) {
        log(`FEJL: ingen .mpy URL for ${hub.label}`);
        return;
    }
    try {
        await hub.flashProgram(url);
    } catch (e) {
        log(`FEJL flash ${hub.label}: ` + (e && e.message ? e.message : String(e)));
    }
}

function hubStatusText(hub) {
    if (!hub.isConnected()) return "Ikke forbundet";
    const name = hub.device ? hub.device.name : "";
    if (!hub.hasStatus) return `Forbundet: ${name} · venter på status`;
    return `Forbundet: ${name} · ${hub.isProgramRunning() ? "Program kører" : "Idle"}`;
}

function hubStatusKind(hub) {
    if (!hub.isConnected()) return "";
    if (!hub.hasStatus) return "ok";
    return hub.isProgramRunning() ? "running" : "ok";
}

function refreshUi() {
    const m = master.isConnected();
    const s = sled.isConnected();
    const dConnected = displays.map((d) => d.isConnected());
    const dCount = dConnected.filter(Boolean).length;
    const totalConnected = (m ? 1 : 0) + (s ? 1 : 0) + dCount;
    const totalHubs = 2 + displays.length;

    // Top-right pill
    ui.hubsBtn.textContent = `Hubs ${totalConnected}/${totalHubs}`;
    ui.hubsBtn.dataset.kind = totalConnected === totalHubs
        ? "ok"
        : (totalConnected === 0 ? "off" : "partial");

    // Master block
    setStatus(ui.status, hubStatusText(master), hubStatusKind(master));
    ui.connect.disabled = m;
    ui.disconnect.disabled = !m;
    ui.startProgram.disabled = !m || master.isProgramRunning() || master.flashing;
    ui.stopProgram.disabled = !m || !master.isProgramRunning();
    if (ui.flashMaster) ui.flashMaster.disabled = !m || master.flashing;

    // Sled block
    setStatus(ui.sledStatus, hubStatusText(sled), hubStatusKind(sled));
    ui.sledConnect.disabled = s;
    ui.sledDisconnect.disabled = !s;
    ui.sledStart.disabled = !s || sled.isProgramRunning() || sled.flashing;
    ui.sledStop.disabled = !s || !sled.isProgramRunning();
    if (ui.flashSled) ui.flashSled.disabled = !s || sled.flashing;

    // Display blocks
    displays.forEach((d, i) => {
        const n = i + 1;
        const connected = d.isConnected();
        setStatus(ui[`display${n}Status`], hubStatusText(d), hubStatusKind(d));
        ui[`display${n}Connect`].disabled = connected;
        ui[`display${n}Disconnect`].disabled = !connected;
        ui[`display${n}Start`].disabled = !connected || d.isProgramRunning() || d.flashing;
        ui[`display${n}Stop`].disabled = !connected || !d.isProgramRunning();
        const flashBtn = ui[`flashDisplay${n}`];
        if (flashBtn) flashBtn.disabled = !connected || d.flashing;
    });

    // Score / pull / sled actions go through master
    ui.sendScore.disabled = !m;
    ui.fullPull.disabled = !m;
    ui.sledButtons.forEach((b) => { b.disabled = !m; });
    ui.sledPushCfg.disabled = !m;
    if (ui.sledPushCfg2) ui.sledPushCfg2.disabled = !m;
}

master.onStateChange = refreshUi;
sled.onStateChange = refreshUi;
displays.forEach((d) => { d.onStateChange = refreshUi; });

// ---------------- Score + sled commands ----------------

async function sendScore(value) {
    const score = Math.max(0, Math.min(999, Number(value) || 0));
    const line = `S ${score}\n`;
    try {
        await master.writeStdin(line);
        log("tx: " + line.trim());
    } catch (err) {
        log("FEJL ved send: " + (err && err.message ? err.message : err));
    }
}

async function sendSledCommand(action, value) {
    const actionId = SLED_ACTIONS[action];
    if (actionId === undefined) {
        log("FEJL: ukendt sled-action " + action);
        return;
    }
    cmdSeq += 1;
    const seq = cmdSeq;
    const v = Math.trunc(Number(value) || 0);
    const line = `C ${seq} ${actionId} ${v}\n`;
    if (ui.lastSeq) ui.lastSeq.textContent = String(seq);
    try {
        await master.writeStdin(line);
        log(`tx: ${action}(${v}) seq=${seq}`);
    } catch (err) {
        log("FEJL sled-cmd: " + (err && err.message ? err.message : err));
    }
}

// ---------------- Config ----------------

const CFG_KEY = "ngtp-sled-config-v1";
const PLATE_WEIGHT_G = 41;

function plateCount() {
    return Math.max(0, Math.round(Number(ui.cfgPlates.value) || 0));
}

function plateWeightG() {
    return plateCount() * PLATE_WEIGHT_G;
}

function loadConfig() {
    try {
        const raw = localStorage.getItem(CFG_KEY);
        if (raw) {
            const c = JSON.parse(raw);
            if (typeof c.ramp_end_m === "number") ui.cfgRamp.value = c.ramp_end_m;
            if (typeof c.full_rotations === "number") ui.cfgRot.value = c.full_rotations;
            if (typeof c.plates === "number") ui.cfgPlates.value = c.plates;
        }
    } catch (e) { }
    renderCfgLabels();
}

function saveConfig() {
    const c = {
        ramp_end_m: Number(ui.cfgRamp.value),
        full_rotations: Number(ui.cfgRot.value),
        plates: plateCount(),
    };
    localStorage.setItem(CFG_KEY, JSON.stringify(c));
}

function renderCfgLabels() {
    ui.cfgRampVal.textContent = String(Number(ui.cfgRamp.value).toFixed(0));
    ui.cfgRotVal.textContent = String(Number(ui.cfgRot.value).toFixed(1));
    if (ui.cfgPlatesVal) ui.cfgPlatesVal.textContent = String(plateCount());
    if (ui.cfgWeightDisplay) ui.cfgWeightDisplay.textContent = String(plateWeightG());
    if (ui.entryWeightPreview) ui.entryWeightPreview.textContent = String(plateWeightG());
}

async function pushConfig() {
    const rampM = Number(ui.cfgRamp.value);
    const rot = Number(ui.cfgRot.value);
    await sendSledCommand("set_ramp_end_m", Math.round(rampM * 10));
    await sendSledCommand("set_full_rotations", Math.round(rot * 10));
    log(`config pushed: ramp_end_m=${rampM} full_rotations=${rot}`);
}

// ---------------- Wire up ----------------

ui.hubsBtn.addEventListener("click", () => ui.hubDialog.showModal());
ui.manualBtn.addEventListener("click", () => ui.manualDialog.showModal());
ui.settingsBtn.addEventListener("click", () => ui.settingsDialog.showModal());

document.querySelectorAll("[data-close-dialog]").forEach((btn) => {
    btn.addEventListener("click", () => {
        const dlg = btn.closest("dialog");
        if (dlg) dlg.close();
    });
});

ui.connect.addEventListener("click", async () => {
    try { await master.connect(); }
    catch (e) {
        setStatus(ui.status, "Forbindelse fejlede", "error");
        log("FEJL master: " + (e && e.message ? e.message : String(e)));
    }
});
ui.disconnect.addEventListener("click", () => master.disconnect());
ui.startProgram.addEventListener("click", async () => {
    try { await master.startProgram(); } catch (e) { log("FEJL start: " + e.message); }
});
ui.stopProgram.addEventListener("click", async () => {
    try { await master.stopProgram(); } catch (e) { log("FEJL stop: " + e.message); }
});

ui.sledConnect.addEventListener("click", async () => {
    try { await sled.connect(); }
    catch (e) {
        setStatus(ui.sledStatus, "Forbindelse fejlede", "error");
        log("FEJL sled: " + (e && e.message ? e.message : String(e)));
    }
});
ui.sledDisconnect.addEventListener("click", () => sled.disconnect());
ui.sledStart.addEventListener("click", async () => {
    try { await sled.startProgram(); } catch (e) { log("FEJL sled start: " + e.message); }
});
ui.sledStop.addEventListener("click", async () => {
    try { await sled.stopProgram(); } catch (e) { log("FEJL sled stop: " + e.message); }
});
ui.sledPushCfg.addEventListener("click", () => pushConfig());
if (ui.sledPushCfg2) ui.sledPushCfg2.addEventListener("click", () => pushConfig());

if (ui.flashMaster) ui.flashMaster.addEventListener("click", () => flashHub(master));
if (ui.flashSled) ui.flashSled.addEventListener("click", () => flashHub(sled));

displays.forEach((d, i) => {
    const n = i + 1;
    const statusEl = ui[`display${n}Status`];
    ui[`display${n}Connect`].addEventListener("click", async () => {
        try { await d.connect(); }
        catch (e) {
            setStatus(statusEl, "Forbindelse fejlede", "error");
            log(`FEJL display${n}: ` + (e && e.message ? e.message : String(e)));
        }
    });
    ui[`display${n}Disconnect`].addEventListener("click", () => d.disconnect());
    ui[`display${n}Start`].addEventListener("click", async () => {
        try { await d.startProgram(); } catch (e) { log(`FEJL display${n} start: ` + e.message); }
    });
    ui[`display${n}Stop`].addEventListener("click", async () => {
        try { await d.stopProgram(); } catch (e) { log(`FEJL display${n} stop: ` + e.message); }
    });
    const flashBtn = ui[`flashDisplay${n}`];
    if (flashBtn) flashBtn.addEventListener("click", () => flashHub(d));
});

ui.sendScore.addEventListener("click", () => sendScore(ui.score.value));
ui.fullPull.addEventListener("click", () => sendScore(10000));

ui.sledButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
        const action = btn.dataset.action;
        let value = 0;
        const fromSel = btn.dataset.valueFrom;
        if (fromSel) {
            const el = document.querySelector(fromSel);
            if (el) value = el.value;
        }
        sendSledCommand(action, value);
    });
});

[ui.cfgRamp, ui.cfgRot].forEach((el) => {
    el.addEventListener("input", () => { renderCfgLabels(); saveConfig(); });
});

// Plate count +/- and input
function setPlates(n) {
    ui.cfgPlates.value = Math.max(0, Math.round(n));
    renderCfgLabels();
    saveConfig();
}
ui.cfgPlates.addEventListener("input", () => { renderCfgLabels(); saveConfig(); });
ui.btnPlatesPlus.addEventListener("click", () => setPlates(plateCount() + 1));
ui.btnPlatesMinus.addEventListener("click", () => setPlates(plateCount() - 1));

// ---------------- Scoreboard ----------------

const SCOREBOARD_KEY = "ngtp-scoreboard-v1";
let scoreboard = [];
let editingId = null;

function loadScoreboard() {
    try {
        const raw = localStorage.getItem(SCOREBOARD_KEY);
        if (raw) scoreboard = JSON.parse(raw) || [];
    } catch (e) { scoreboard = []; }
    renderScoreboard();
}

function saveScoreboardStore() {
    localStorage.setItem(SCOREBOARD_KEY, JSON.stringify(scoreboard));
}

function getLiveDistanceM() {
    const txt = ui.distance.textContent.trim();
    const m = txt.match(/-?\d+(\.\d+)?/);
    return m ? Number(m[0]) : 0;
}

function newId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

function fmtTime(ms) {
    return new Date(ms).toLocaleString("da-DK", { hour12: false });
}

function fmtWeight(g) {
    if (g >= 1000) return (g / 1000).toFixed(2) + " kg";
    return g + " g";
}

function renderScoreboard() {
    const tbody = ui.scoreboardBody;
    if (!tbody) return;
    tbody.innerHTML = "";
    const rows = [...scoreboard].sort((a, b) => b.time - a.time);
    for (const e of rows) {
        const tr = document.createElement("tr");
        const tdName = document.createElement("td");
        tdName.textContent = e.name || "";
        const tdWeight = document.createElement("td");
        tdWeight.textContent = fmtWeight(e.weight_g || 0);
        const tdDist = document.createElement("td");
        tdDist.textContent = (Number(e.distance_m) || 0).toFixed(1) + " m";
        const tdEdit = document.createElement("td");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-edit";
        btn.dataset.id = e.id;
        btn.textContent = "✎";
        tdEdit.appendChild(btn);
        tr.append(tdName, tdWeight, tdDist, tdEdit);
        tbody.appendChild(tr);
    }

    // Datalist of known names
    if (ui.knownNames) {
        const names = [...new Set(scoreboard.map((s) => (s.name || "").trim()).filter(Boolean))].sort();
        ui.knownNames.innerHTML = "";
        for (const n of names) {
            const opt = document.createElement("option");
            opt.value = n;
            ui.knownNames.appendChild(opt);
        }
    }
}

function addEntry() {
    const name = (ui.entryName.value || "").trim();
    if (!name) {
        ui.entryName.focus();
        return;
    }
    const entry = {
        id: newId(),
        time: Date.now(),
        name,
        weight_g: plateWeightG(),
        distance_m: getLiveDistanceM(),
    };
    scoreboard.push(entry);
    saveScoreboardStore();
    renderScoreboard();
    ui.entryName.value = "";
}

function localIsoForInput(ms) {
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function openEdit(id) {
    const e = scoreboard.find((x) => x.id === id);
    if (!e) return;
    editingId = id;
    ui.editTime.value = localIsoForInput(e.time);
    ui.editName.value = e.name || "";
    ui.editWeight.value = e.weight_g || 0;
    ui.editDistance.value = (Number(e.distance_m) || 0).toFixed(1);
    ui.editDialog.showModal();
}

function saveEdit() {
    const e = scoreboard.find((x) => x.id === editingId);
    if (!e) return;
    const t = ui.editTime.value ? new Date(ui.editTime.value).getTime() : e.time;
    e.time = Number.isFinite(t) ? t : e.time;
    e.name = (ui.editName.value || "").trim();
    e.weight_g = Math.max(0, Math.round(Number(ui.editWeight.value) || 0));
    e.distance_m = Math.max(0, Number(ui.editDistance.value) || 0);
    saveScoreboardStore();
    renderScoreboard();
    ui.editDialog.close();
}

function deleteEdit() {
    scoreboard = scoreboard.filter((x) => x.id !== editingId);
    saveScoreboardStore();
    renderScoreboard();
    ui.editDialog.close();
}

ui.btnAddEntry.addEventListener("click", addEntry);
ui.scoreboardBody.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btn-edit");
    if (btn) openEdit(btn.dataset.id);
});
ui.btnEditSave.addEventListener("click", saveEdit);
ui.btnEditDelete.addEventListener("click", deleteEdit);

// Force reload: unregister SW, clear caches, reload.
const btnForceReload = document.getElementById("btn-force-reload");
if (btnForceReload) {
    btnForceReload.addEventListener("click", async () => {
        btnForceReload.disabled = true;
        btnForceReload.textContent = "Rydder...";
        try {
            if ("serviceWorker" in navigator) {
                const regs = await navigator.serviceWorker.getRegistrations();
                await Promise.all(regs.map((r) => r.unregister()));
            }
            if ("caches" in window) {
                const keys = await caches.keys();
                await Promise.all(keys.map((k) => caches.delete(k)));
            }
        } catch (e) { /* ignore */ }
        // Bypass HTTP cache too.
        const url = new URL(window.location.href);
        url.searchParams.set("_", Date.now().toString());
        window.location.replace(url.toString());
    });
}

loadConfig();
loadScoreboard();
refreshUi();

if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("./sw.js").catch(() => { });
    });
}
