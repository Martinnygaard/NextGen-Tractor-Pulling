// Pybricks Profile BLE UUIDs.
const PYBRICKS_SERVICE = "c5f50001-8280-46da-89f4-6d8051e4aeef";
const PYBRICKS_COMMAND_EVENT_CHAR = "c5f50002-8280-46da-89f4-6d8051e4aeef";

const CMD_STOP_USER_PROGRAM = 0x00;
const CMD_START_USER_PROGRAM = 0x01;
const CMD_WRITE_STDIN = 0x06;
const EVT_WRITE_STDOUT = 0x01;

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
        this.commandChar = null;
        this.stdoutBuffer = "";
        this.onStateChange = () => { };
    }

    isConnected() {
        return !!this.commandChar;
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
            this.server = null;
            this.onStateChange();
        });
        this.server = await this.device.gatt.connect();
        const service = await this.server.getPrimaryService(PYBRICKS_SERVICE);
        this.commandChar = await service.getCharacteristic(PYBRICKS_COMMAND_EVENT_CHAR);
        await this.commandChar.startNotifications();
        this.commandChar.addEventListener("characteristicvaluechanged", (e) => this._onEvent(e));
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

function refreshUi() {
    const m = master.isConnected();
    const s = sled.isConnected();
    const count = (m ? 1 : 0) + (s ? 1 : 0);

    // Top-right pill
    ui.hubsBtn.textContent = `Hubs ${count}/2`;
    ui.hubsBtn.dataset.kind = count === 2 ? "ok" : (count === 0 ? "off" : "partial");

    // Master block
    setStatus(ui.status, m ? `Forbundet: ${master.device.name}` : "Ikke forbundet", m ? "ok" : "");
    ui.connect.disabled = m;
    ui.disconnect.disabled = !m;
    ui.startProgram.disabled = !m;
    ui.stopProgram.disabled = !m;

    // Sled block
    setStatus(ui.sledStatus, s ? `Forbundet: ${sled.device.name}` : "Ikke forbundet", s ? "ok" : "");
    ui.sledConnect.disabled = s;
    ui.sledDisconnect.disabled = !s;
    ui.sledStart.disabled = !s;
    ui.sledStop.disabled = !s;

    // Score / pull / sled actions go through master
    ui.sendScore.disabled = !m;
    ui.fullPull.disabled = !m;
    ui.sledButtons.forEach((b) => { b.disabled = !m; });
    ui.sledPushCfg.disabled = !m;
    if (ui.sledPushCfg2) ui.sledPushCfg2.disabled = !m;
}

master.onStateChange = refreshUi;
sled.onStateChange = refreshUi;

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

function loadConfig() {
    try {
        const raw = localStorage.getItem(CFG_KEY);
        if (raw) {
            const c = JSON.parse(raw);
            if (typeof c.ramp_end_m === "number") ui.cfgRamp.value = c.ramp_end_m;
            if (typeof c.full_rotations === "number") ui.cfgRot.value = c.full_rotations;
        }
    } catch (e) { }
    renderCfgLabels();
}

function saveConfig() {
    const c = {
        ramp_end_m: Number(ui.cfgRamp.value),
        full_rotations: Number(ui.cfgRot.value),
    };
    localStorage.setItem(CFG_KEY, JSON.stringify(c));
}

function renderCfgLabels() {
    ui.cfgRampVal.textContent = String(Number(ui.cfgRamp.value).toFixed(0));
    ui.cfgRotVal.textContent = String(Number(ui.cfgRot.value).toFixed(1));
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

loadConfig();
refreshUi();

if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("./sw.js").catch(() => { });
    });
}
