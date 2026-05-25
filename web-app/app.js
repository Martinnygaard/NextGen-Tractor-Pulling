// Pybricks Profile BLE UUIDs.
// See: https://github.com/pybricks/technical-info/blob/master/pybricks-ble-profile.md
const PYBRICKS_SERVICE = "c5f50001-8280-46da-89f4-6d8051e4aeef";
const PYBRICKS_COMMAND_EVENT_CHAR = "c5f50002-8280-46da-89f4-6d8051e4aeef";

// Command IDs (host -> hub).
const CMD_STOP_USER_PROGRAM = 0x00;
const CMD_START_USER_PROGRAM = 0x01;
const CMD_WRITE_STDIN = 0x06;

// Event IDs (hub -> host).
const EVT_STATUS_REPORT = 0x00;
const EVT_WRITE_STDOUT = 0x01;

// Sled command actions (must match hubs/sled.py CMD_* constants).
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
};

const ui = {
    connect: document.getElementById("btn-connect"),
    disconnect: document.getElementById("btn-disconnect"),
    startProgram: document.getElementById("btn-start-program"),
    stopProgram: document.getElementById("btn-stop-program"),
    sendScore: document.getElementById("btn-send-score"),
    fullPull: document.getElementById("btn-full-pull"),
    score: document.getElementById("score"),
    status: document.getElementById("status"),
    log: document.getElementById("log"),
    distance: document.getElementById("distance"),
    lastAck: document.getElementById("last-ack"),
    lastSeq: document.getElementById("last-seq"),
    sledButtons: document.querySelectorAll(".sled-action"),
};

let device = null;
let server = null;
let commandChar = null;
let stdoutBuffer = "";
let cmdSeq = 0; // local sequence counter for sled commands (phone-assigned)

function setStatus(text, kind) {
    ui.status.textContent = text;
    ui.status.dataset.kind = kind || "";
}

function log(line) {
    const ts = new Date().toLocaleTimeString("da-DK", { hour12: false });
    ui.log.textContent += `[${ts}] ${line}\n`;
    ui.log.scrollTop = ui.log.scrollHeight;
}

function setConnectedUi(connected) {
    ui.connect.disabled = connected;
    ui.disconnect.disabled = !connected;
    if (ui.startProgram) ui.startProgram.disabled = !connected;
    if (ui.stopProgram) ui.stopProgram.disabled = !connected;
    ui.sendScore.disabled = !connected;
    ui.fullPull.disabled = !connected;
    ui.sledButtons.forEach((b) => { b.disabled = !connected; });
}

function setDistance(meters) {
    if (!ui.distance) return;
    ui.distance.textContent = meters.toFixed(1) + " m";
}

async function connect() {
    if (!("bluetooth" in navigator)) {
        setStatus("Web Bluetooth ikke tilgængelig", "error");
        log("FEJL: Browser understøtter ikke Web Bluetooth. Brug Chrome eller Edge.");
        return;
    }

    try {
        setStatus("Vælger enhed...");
        device = await navigator.bluetooth.requestDevice({
            filters: [{ namePrefix: "Puller" }],
            optionalServices: [PYBRICKS_SERVICE],
        });
        device.addEventListener("gattserverdisconnected", onDisconnected);

        setStatus("Forbinder...");
        server = await device.gatt.connect();

        const service = await server.getPrimaryService(PYBRICKS_SERVICE);
        commandChar = await service.getCharacteristic(PYBRICKS_COMMAND_EVENT_CHAR);
        await commandChar.startNotifications();
        commandChar.addEventListener("characteristicvaluechanged", onEvent);

        setStatus(`Forbundet: ${device.name}`, "ok");
        log(`Forbundet til ${device.name}`);
        setConnectedUi(true);
    } catch (err) {
        setStatus("Forbindelse fejlede", "error");
        log("FEJL: " + (err && err.message ? err.message : String(err)));
        setConnectedUi(false);
    }
}

function onDisconnected() {
    setStatus("Afbrudt", "error");
    log("Hub afbrød forbindelsen");
    setConnectedUi(false);
    commandChar = null;
    server = null;
}

async function disconnect() {
    if (device && device.gatt && device.gatt.connected) {
        device.gatt.disconnect();
    }
}

function handleHubLine(line) {
    // D <integer>  -> live distance from sled, encoded as tenths of a meter.
    if (line.startsWith("D ")) {
        const v = parseInt(line.slice(2).trim(), 10);
        if (!Number.isNaN(v)) {
            setDistance(v / 10);
        }
        return;
    }
    // A <seq>  -> sled acknowledged command seq
    if (line.startsWith("A ")) {
        const v = parseInt(line.slice(2).trim(), 10);
        if (!Number.isNaN(v) && ui.lastAck) {
            ui.lastAck.textContent = String(v);
        }
        return;
    }
}

function onEvent(event) {
    const dv = event.target.value;
    if (!dv || dv.byteLength < 1) return;
    const data = new Uint8Array(dv.buffer, dv.byteOffset, dv.byteLength);
    const evtId = data[0];

    if (evtId === EVT_WRITE_STDOUT) {
        const text = new TextDecoder().decode(data.subarray(1));
        stdoutBuffer += text;
        let idx;
        while ((idx = stdoutBuffer.indexOf("\n")) >= 0) {
            const line = stdoutBuffer.slice(0, idx).replace(/\r$/, "");
            stdoutBuffer = stdoutBuffer.slice(idx + 1);
            if (!line.length) continue;
            handleHubLine(line);
            log("hub: " + line);
        }
    } else if (evtId === EVT_STATUS_REPORT) {
        // First 4 bytes after evtId are a uint32 bitfield of hub status flags.
    } else {
        log(`evt 0x${evtId.toString(16)} (${data.byteLength}B)`);
    }
}

async function writeStdin(text) {
    if (!commandChar) throw new Error("Not connected");
    const bytes = new TextEncoder().encode(text);
    const CHUNK = 18;
    for (let offset = 0; offset < bytes.length; offset += CHUNK) {
        const slice = bytes.subarray(offset, offset + CHUNK);
        const frame = new Uint8Array(1 + slice.length);
        frame[0] = CMD_WRITE_STDIN;
        frame.set(slice, 1);
        await commandChar.writeValueWithResponse(frame);
    }
}

async function sendScore(value) {
    const score = Math.max(0, Math.min(999, Number(value) || 0));
    const line = `S ${score}\n`;
    try {
        await writeStdin(line);
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
        await writeStdin(line);
        log(`tx: ${action}(${v}) seq=${seq}`);
    } catch (err) {
        log("FEJL sled-cmd: " + (err && err.message ? err.message : err));
    }
}

async function startProgram() {
    if (!commandChar) return;
    try {
        await commandChar.writeValueWithResponse(new Uint8Array([CMD_START_USER_PROGRAM, 0]));
        log("tx: START_USER_PROGRAM");
    } catch (err) {
        log("FEJL start: " + (err && err.message ? err.message : err));
    }
}

async function stopProgram() {
    if (!commandChar) return;
    try {
        await commandChar.writeValueWithResponse(new Uint8Array([CMD_STOP_USER_PROGRAM]));
        log("tx: STOP_USER_PROGRAM");
    } catch (err) {
        log("FEJL stop: " + (err && err.message ? err.message : err));
    }
}

ui.connect.addEventListener("click", connect);
ui.disconnect.addEventListener("click", disconnect);
if (ui.startProgram) ui.startProgram.addEventListener("click", startProgram);
if (ui.stopProgram) ui.stopProgram.addEventListener("click", stopProgram);
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

// Register service worker for PWA install (optional, fails silently in dev).
if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("./sw.js").catch(() => { });
    });
}
