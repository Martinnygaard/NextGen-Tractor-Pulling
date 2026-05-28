// Pybricks Profile BLE UUIDs.
const PYBRICKS_SERVICE = "c5f50001-8280-46da-89f4-6d8051e4aeef";
const PYBRICKS_COMMAND_EVENT_CHAR = "c5f50002-8280-46da-89f4-6d8051e4aeef";
const PYBRICKS_HUB_CAPS_CHAR = "c5f50003-8280-46da-89f4-6d8051e4aeef";
// Nordic UART Service. Pybricks Profile v1.0–1.2 routed program stdio
// through here. Pybricks Profile v1.3+ moved stdout to EVT_WRITE_STDOUT
// on the Pybricks command/event char, but on some firmware builds the
// hub still emits program output on NUS TX. Subscribe to both.
const NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
const NUS_TX_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"; // hub → host
const NUS_RX_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"; // host → hub
// Standard Device Information Service / Software Revision String.
const DEVICE_INFO_SERVICE = 0x180a;
const SOFTWARE_REVISION_CHAR = 0x2a28;
const FIRMWARE_REVISION_CHAR = 0x2a26;

const CMD_STOP_USER_PROGRAM = 0x00;
const CMD_START_USER_PROGRAM = 0x01;
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

    // Sled
    sledConnect: document.getElementById("btn-sled-connect"),
    sledDisconnect: document.getElementById("btn-sled-disconnect"),
    sledStart: document.getElementById("btn-sled-start"),
    sledStop: document.getElementById("btn-sled-stop"),
    sledPushCfg: document.getElementById("btn-push-config"),
    sledPushCfg2: document.getElementById("btn-push-config-2"),
    sledStatus: document.getElementById("sled-status"),

    // Sled actions (manual)
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
        this.nusRx = null;
        this.maxWriteSize = 20; // ATT default; may be raised after connect
        this.stdoutBuffer = "";
        this.statusFlags = 0;
        this.hasStatus = false;
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
            optionalServices: [PYBRICKS_SERVICE, NUS_SERVICE, DEVICE_INFO_SERVICE],
        });
        this.device.addEventListener("gattserverdisconnected", () => {
            log(`${this.label}: afbrudt`);
            this.commandChar = null;
            this.nusRx = null;
            this.service = null;
            this.server = null;
            this.statusFlags = 0;
            this.hasStatus = false;
            this._cmdUseNoResp = undefined;
            this._ramFallbackLogged = false;
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
            // Layout per Pybricks Profile: u16 maxWriteSize, u32 flags,
            // u32 maxUserProgSize, optional u8 numOfSlots (v1.5+).
            // Log the raw bytes + decoded flags so we can compare hubs.
            const hex = [];
            for (let i = 0; i < caps.byteLength; i++) {
                hex.push(caps.getUint8(i).toString(16).padStart(2, "0"));
            }
            let flagsStr = "";
            if (caps.byteLength >= 6) {
                const f = caps.getUint32(2, true);
                const names = [];
                if (f & 0x01) names.push("HasRepl");
                if (f & 0x02) names.push("MultiMpy6");
                if (f & 0x04) names.push("MultiMpy6Native6.1");
                if (f & 0x08) names.push("HasPortView");
                if (f & 0x10) names.push("HasIMUCalibration");
                flagsStr = ` flags=0x${f.toString(16)} [${names.join(",")}]`;
                if (caps.byteLength >= 10) {
                    const maxProg = caps.getUint32(6, true);
                    flagsStr += ` maxProgSize=${maxProg}`;
                }
                if (caps.byteLength >= 11) {
                    flagsStr += ` slots=${caps.getUint8(10)}`;
                }
            }
            log(`${this.label}: caps=${hex.join(" ")}${flagsStr}`);
        } catch (e) {
            // Older firmware may not expose the capability characteristic.
        }

        // Read Software Revision (= Pybricks Profile version) so we know
        // whether the hub routes stdout through EVT_WRITE_STDOUT
        // (Profile v1.3+) or only through the Nordic UART Service
        // (Profile <= v1.2).
        try {
            const infoSvc = await this.server.getPrimaryService(DEVICE_INFO_SERVICE);
            try {
                const swChar = await infoSvc.getCharacteristic(SOFTWARE_REVISION_CHAR);
                const sw = await swChar.readValue();
                const swStr = new TextDecoder().decode(sw);
                log(`${this.label}: Pybricks Profile = ${swStr}`);
            } catch (e) { /* ignore */ }
            try {
                const fwChar = await infoSvc.getCharacteristic(FIRMWARE_REVISION_CHAR);
                const fw = await fwChar.readValue();
                const fwStr = new TextDecoder().decode(fw);
                log(`${this.label}: firmware = ${fwStr}`);
            } catch (e) { /* ignore */ }
        } catch (e) {
            log(`${this.label}: device info service utilgængelig (${e && e.message ? e.message : e})`);
        }

        // Subscribe to Nordic UART Service TX (hub -> host) so we catch
        // any program stdout the firmware routes through NUS instead of
        // the Pybricks event char. Notifications are forwarded into the
        // same stdout buffer/handler used for EVT_WRITE_STDOUT.
        try {
            const nusSvc = await this.server.getPrimaryService(NUS_SERVICE);
            try {
                const nusTx = await nusSvc.getCharacteristic(NUS_TX_CHAR);
                await nusTx.startNotifications();
                nusTx.addEventListener("characteristicvaluechanged", (e) => this._onNusEvent(e));
                log(`${this.label}: NUS TX subscribed (stdout fallback)`);
            } catch (e) {
                log(`${this.label}: NUS TX utilgængelig (${e && e.message ? e.message : e})`);
            }
            // Also grab NUS RX (host -> hub) so we can write stdin directly.
            // Pybricks 3.6+ routes raw bytes written here straight into the
            // running program's stdin queue (which read_input_byte reads).
            try {
                this.nusRx = await nusSvc.getCharacteristic(NUS_RX_CHAR);
                log(`${this.label}: NUS RX claimed (stdin path)`);
            } catch (e) {
                this.nusRx = null;
                log(`${this.label}: NUS RX utilgængelig (${e && e.message ? e.message : e})`);
            }
        } catch (e) {
            log(`${this.label}: NUS service utilgængelig (${e && e.message ? e.message : e})`);
        }

        log(`${this.label}: forbundet til ${this.device.name}`);
        try {
            const p = this.commandChar.properties || {};
            const flags = [];
            if (p.write) flags.push("write");
            if (p.writeWithoutResponse) flags.push("writeWithoutResponse");
            if (p.notify) flags.push("notify");
            log(`${this.label}: cmd char props=${flags.join(",") || "?"}`);
        } catch (_) { /* ignore */ }
        this.onStateChange();
    }

    async disconnect() {
        if (this.device && this.device.gatt && this.device.gatt.connected) {
            this.device.gatt.disconnect();
        }
    }

    _onNusEvent(event) {
        // Pybricks Profile <= v1.2 routes program stdio through the
        // Nordic UART Service. The payload here is just raw bytes
        // (no event-id prefix), so feed it straight into the stdout
        // line buffer.
        const dv = event.target.value;
        if (!dv || dv.byteLength < 1) return;
        const data = new Uint8Array(dv.buffer, dv.byteOffset, dv.byteLength);
        const hex = Array.from(data)
            .slice(0, 32)
            .map((b) => b.toString(16).padStart(2, "0"))
            .join(" ");
        log(`${this.label}: NUS RX len=${data.byteLength} [${hex}${data.byteLength > 32 ? " …" : ""}]`);
        const text = new TextDecoder().decode(data);
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

    _onEvent(event) {
        const dv = event.target.value;
        if (!dv || dv.byteLength < 1) return;
        const data = new Uint8Array(dv.buffer, dv.byteOffset, dv.byteLength);
        const evtId = data[0];
        // Diagnostic: log every non-status event so we can see if the hub
        // sends stdout under a different event id or with unexpected
        // framing. Status reports are far too noisy to log raw.
        if (evtId !== EVT_STATUS_REPORT) {
            const hex = Array.from(data)
                .slice(0, 32)
                .map((b) => b.toString(16).padStart(2, "0"))
                .join(" ");
            log(`${this.label}: BLE evt id=0x${evtId.toString(16)} len=${data.byteLength} [${hex}${data.byteLength > 32 ? " …" : ""}]`);
        }
        if (evtId === EVT_STATUS_REPORT) {
            if (data.byteLength >= 5) {
                // uint32 little-endian status bitfield.
                const flags = data[1] | (data[2] << 8) | (data[3] << 16) | (data[4] << 24);
                const prev = this.statusFlags;
                const wasFirst = !this.hasStatus;
                this.statusFlags = flags >>> 0;
                this.hasStatus = true;
                const progId = data.byteLength > 5 ? data[5] : 0;
                const slot = data.byteLength > 6 ? data[6] : 0;
                if (wasFirst) {
                    log(`${this.label}: første status flags=0x${flags.toString(16)} progId=${progId} slot=${slot} bytes=${data.byteLength}`);
                } else if (((prev ^ flags) & STATUS_USER_PROGRAM_RUNNING) !== 0) {
                    log(`${this.label}: program ${this.isProgramRunning() ? "kører" : "stoppet"} (flags=0x${flags.toString(16)} progId=${progId} slot=${slot})`);
                } else if (prev !== flags) {
                    // Non-running-flag transitions are still interesting
                    // while we debug. Avoid spamming when nothing changes.
                    log(`${this.label}: status flags=0x${flags.toString(16)} (var 0x${prev.toString(16)}) progId=${progId} slot=${slot}`);
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
        // Preferred path: Pybricks 3.6+ accepts raw stdin bytes on the
        // Nordic UART RX char. The command-char WRITE_STDIN opcode (0x06)
        // is silently dropped on profile 1.4+, so fall back to it only if
        // NUS RX isn't available.
        if (this.nusRx) {
            const CHUNK = 20;
            for (let off = 0; off < bytes.length; off += CHUNK) {
                const slice = bytes.subarray(off, off + CHUNK);
                try {
                    await this.nusRx.writeValueWithoutResponse(slice);
                } catch (e) {
                    await this.nusRx.writeValueWithResponse(slice);
                }
            }
            return;
        }
        const CHUNK = 18;
        for (let off = 0; off < bytes.length; off += CHUNK) {
            const slice = bytes.subarray(off, off + CHUNK);
            const frame = new Uint8Array(1 + slice.length);
            frame[0] = CMD_WRITE_STDIN;
            frame.set(slice, 1);
            await this._writeCommand(frame);
        }
    }

    async _writeCommand(buf) {
        // pybricks-code uses writeValueWithoutResponse on the command char.
        // Some hubs report only "write" in Chrome but still accept the
        // no-response write (Chrome property enumeration bug), and crucially
        // a write-with-response on these hubs fails with "GATT Error
        // Unknown" for commands that trigger slow firmware work like
        // WRITE_USER_PROGRAM_META. So try without-response first, fall back.
        if (!this.commandChar) throw new Error(`${this.label} ikke forbundet`);
        if (this._cmdUseNoResp !== false) {
            try {
                await this.commandChar.writeValueWithoutResponse(buf);
                return;
            } catch (e) {
                if (this._cmdUseNoResp === undefined) {
                    log(`${this.label}: write-without-response gav ${e && e.message ? e.message : e}, falder tilbage til with-response`);
                }
                this._cmdUseNoResp = false;
            }
        }
        await this.commandChar.writeValueWithResponse(buf);
    }

    async startProgram() {
        if (!this.commandChar) return;
        // Use with-response so we actually see GATT errors (e.g. "no program
        // in slot 0"). If the firmware doesn't accept the 2-byte form, fall
        // back to the legacy 1-byte START.
        try {
            await this.commandChar.writeValueWithResponse(
                new Uint8Array([CMD_START_USER_PROGRAM, 0]),
            );
            log(`${this.label}: START_USER_PROGRAM (slot 0)`);
        } catch (e) {
            log(`${this.label}: START [0x01,0x00] fejlede (${e && e.message ? e.message : e}) — prøver legacy [0x01]`);
            try {
                await this.commandChar.writeValueWithResponse(
                    new Uint8Array([CMD_START_USER_PROGRAM]),
                );
                log(`${this.label}: START_USER_PROGRAM (legacy)`);
            } catch (e2) {
                log(`${this.label}: START fejlede helt (${e2 && e2.message ? e2.message : e2}) — er programmet flashet via deploy.py?`);
                throw e2;
            }
        }
    }

    async stopProgram() {
        if (!this.commandChar) return;
        await this._writeCommand(new Uint8Array([CMD_STOP_USER_PROGRAM]));
        log(`${this.label}: STOP_USER_PROGRAM`);
    }
}

// ---------------- Hub instances ----------------

// PWA talks ONLY to the sled. Sled broadcasts distance/full-pull on
// BLE channel 2; the display hubs observe that channel directly and
// require no involvement from the PWA. Sled commands (start/stop/etc)
// are written to Pybricks stdin over the Nordic UART RX char.
const sled = new HubConnection("sled", "Puller Sled", (line) => {
    // Sled prints "DBG mode=... lane_m=X.Y sled_pct=Z events=..."
    // once a second. Parse lane_m to drive the live distance card.
    const m = line.match(/lane_m=(-?\d+(?:\.\d+)?)/);
    if (m) {
        const v = parseFloat(m[1]);
        if (!Number.isNaN(v)) setDistance(v);
    }
});

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
    const s = sled.isConnected();

    // Top-right pill: shows just "Slæde" - colored by connection state.
    ui.hubsBtn.textContent = "Slæde";
    ui.hubsBtn.dataset.kind = s ? "ok" : "off";

    // Sled block
    setStatus(ui.sledStatus, hubStatusText(sled), hubStatusKind(sled));
    ui.sledConnect.disabled = s;
    ui.sledDisconnect.disabled = !s;
    ui.sledStart.disabled = !s || sled.isProgramRunning();
    ui.sledStop.disabled = !s || !sled.isProgramRunning();

    // Pull / manual / push-config buttons require sled program running.
    const sledReady = s && sled.isProgramRunning();
    ui.sledButtons.forEach((b) => { b.disabled = !sledReady; });
    ui.sledPushCfg.disabled = !sledReady;
    if (ui.sledPushCfg2) ui.sledPushCfg2.disabled = !sledReady;
}

sled.onStateChange = refreshUi;

// ---------------- Sled commands ----------------

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
        await sled.writeStdin(line);
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

// Debounced auto-push of ramp_end_m / full_rotations to the sled
// whenever the slider/input changes - so the operator doesn't have to
// remember to hit "Push til hub" after tweaking calibration.
let _cfgAutoPushTimer = null;
function scheduleAutoPushConfig() {
    if (_cfgAutoPushTimer) clearTimeout(_cfgAutoPushTimer);
    _cfgAutoPushTimer = setTimeout(async () => {
        _cfgAutoPushTimer = null;
        if (!sled || !sled.isConnected || !sled.isConnected()) return;
        try { await pushConfig(); } catch (e) { log("FEJL auto-push config: " + e.message); }
    }, 400);
}

[ui.cfgRamp, ui.cfgRot].forEach((el) => {
    el.addEventListener("input", () => { renderCfgLabels(); saveConfig(); scheduleAutoPushConfig(); });
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
