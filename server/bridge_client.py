import json
import os
import sys
import time
import asyncio
import subprocess
import threading
import traceback
from pathlib import Path
from urllib import error, parse, request


SERVER_URL = os.environ.get("NGTP_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
POLL_INTERVAL = float(os.environ.get("NGTP_BRIDGE_POLL_SECONDS", "0.25"))
MODE = os.environ.get("NGTP_BRIDGE_MODE", "loopback").lower()
PYBRICKS_SCOREBOARD_HUB = os.environ.get("NGTP_SCOREBOARD_HUB", "")
PYBRICKS_SLED_HUB = os.environ.get("NGTP_SLED_HUB", "")
PYBRICKS_DISPLAY_1_HUB = os.environ.get("NGTP_DISPLAY_1_HUB", "")
PYBRICKS_DISPLAY_2_HUB = os.environ.get("NGTP_DISPLAY_2_HUB", "")
PYBRICKS_DISPLAY_3_HUB = os.environ.get("NGTP_DISPLAY_3_HUB", "")
PYBRICKS_TIMEOUT = float(os.environ.get("NGTP_PYBRICKS_TIMEOUT_SECONDS", "20"))
DEBUG_HUB_TX = os.environ.get("NGTP_BRIDGE_DEBUG_TX", "0").lower() in ("1", "true", "yes", "on")


def _is_noisy_hub_line(text):
    """Return True for verbose periodic hub lines that should be hidden
    unless NGTP_BRIDGE_DEBUG_TX is enabled."""
    return text.startswith("TX ")


class HubUnavailable(Exception):
    """Raised when a command can't be delivered because the target hub is
    not currently connected. Treated as a soft-skip: the command stays in
    the server queue, no traceback is printed."""

REPO_ROOT = Path(__file__).resolve().parent.parent
HUBS_DIR = REPO_ROOT / "hubs"
MASTER_SCRIPT = HUBS_DIR / "master_broadcaster.py"
SLED_SCRIPT = HUBS_DIR / "sled.py"
DISPLAY_1_SCRIPT = HUBS_DIR / "display_1.py"
DISPLAY_2_SCRIPT = HUBS_DIR / "display_2.py"
DISPLAY_3_SCRIPT = HUBS_DIR / "display_3.py"

# Must match hubs/sled.py CMD_* constants.
SLED_ACTION_MAP = {
    "start_pull": 1,
    "stop_pull": 2,
    "home_weight": 3,
    "set_signal_red": 4,
    "set_signal_green": 5,
    "set_weight_percent": 6,
    "reset_distance": 7,
    "clear_signal": 8,
    "set_signal_green_blink": 9,
    "set_ramp_end_m": 10,
    "set_full_rotations": 11,
}


class HttpClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def get_json(self, path, query=None):
        url = self.base_url + path
        if query:
            url += "?" + parse.urlencode(query)
        req = request.Request(url=url, method="GET")
        return self._send(req)

    def post_json(self, path, payload=None):
        url = self.base_url + path
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(url=url, data=data, headers=headers, method="POST")
        return self._send(req)

    def _send(self, req):
        with request.urlopen(req, timeout=5) as response:
            body = response.read()
        if not body:
            return None
        return json.loads(body.decode("utf-8"))


class BaseAdapter:
    def handle_sled(self, client, command):
        raise NotImplementedError

    def handle_scoreboard(self, client, command):
        raise NotImplementedError

    def ack_immediately(self, target):
        """Return True if main loop should ack the server right after
        handle_*. Adapters that wait for a hub ack should return False
        for that target and provide acks via drain_pending_acks()."""
        return True

    def drain_pending_acks(self):
        """Return a list of (target, cmd_id) ready to ack to the server."""
        return []

    def start(self):
        """Optional eager initialization hook. Called once at bridge startup."""
        return


class LoopbackAdapter(BaseAdapter):
    def handle_sled(self, client, command):
        payload = command.get("payload", {})
        action = payload.get("action")
        value = payload.get("value")
        print("SLED", action, value)

        # Optional loopback behavior for quick local testing.
        # If you want to see distance movement in UI without hardware,
        # set distance via set_mode value in range 0..100.
        if action == "set_mode" and value is not None:
            try:
                distance = float(value)
                client.post_json("/api/distance/%s" % distance)
            except Exception:
                pass

    def handle_scoreboard(self, client, command):
        payload = command.get("payload", {})
        action = payload.get("action")
        value = payload.get("value")

        if action == "set_score":
            client.post_json("/api/score/%d" % int(value or 0))
        elif action == "full_pull":
            client.post_json("/api/full-pull")
        elif action == "blank":
            client.post_json("/api/reset")
        elif action == "reset":
            client.post_json("/api/reset")


class LoggingAdapter(BaseAdapter):
    def handle_sled(self, client, command):
        print("SLED", json.dumps(command))

    def handle_scoreboard(self, client, command):
        print("SCOREBOARD", json.dumps(command))


class PybricksExecAdapter(BaseAdapter):
    """Connects to the master hub via Pybricks BLE, downloads
    `master_broadcaster.py`, and uses the Pybricks NUS stdin channel to send
    `S <score>` and `C <seq> <action> <value>` lines. Hub stdout is parsed
    for `D <distance>` (forward to /api/distance) and `A <seq>` (ack the
    matching sled command back to the server)."""

    def __init__(self, scoreboard_hub, sled_hub, timeout_seconds, http_client,
                 display_1_hub="", display_2_hub="", display_3_hub=""):
        self.scoreboard_hub = scoreboard_hub.strip()
        self.sled_hub = sled_hub.strip()
        self.display_1_hub = display_1_hub.strip()
        self.display_2_hub = display_2_hub.strip()
        self.display_3_hub = display_3_hub.strip()
        self.timeout_seconds = timeout_seconds
        self._http = http_client
        self._lock = threading.Lock()
        self._cmd_seq = 0
        self._pending_bridge = {}   # bridge_seq -> cmd_id (awaiting ASSIGN)
        self._pending_sled = {}     # broadcast_seq -> cmd_id
        self._ready_acks = []       # list of (target, cmd_id)
        self._ready_acks_lock = threading.Lock()

        self._loop = None
        self._loop_thread = None
        self._hub = None
        self._aux_hubs = []         # keep references so connections stay alive
        self._aux_config = {}       # label -> (name, script_path) for reconnect
        self._hub_states_lock = threading.Lock()
        self._hub_states = {}       # label -> dict
        self._reconnect_in_progress = set()
        self._reboot_in_progress = set()
        self._release_in_progress = set()
        self._released = set()          # labels explicitly released; skip auto-reconnect
        self._last_auto_reconnect = {}  # label -> ts of last auto attempt
        self._connected_event = threading.Event()
        self._connect_error = None
        self._stdout_buf = b""

    # --------------------- BLE connection / event loop ---------------------

    def _set_hub_state(self, label, name, connected, error=None):
        with self._hub_states_lock:
            self._hub_states[label] = {
                "label": label,
                "name": name or "",
                "connected": bool(connected),
                "error": (None if error is None else str(error)),
                "ts": time.time(),
            }

    def get_hub_states(self):
        with self._hub_states_lock:
            return list(self._hub_states.values())

    def request_reconnect(self, label):
        if self._loop is None:
            return False
        if label in self._reconnect_in_progress:
            return False
        # Manual reconnect cancels any prior release so auto-reconnect resumes.
        self._released.discard(label)
        self._reconnect_in_progress.add(label)
        asyncio.run_coroutine_threadsafe(self._reconnect_label(label), self._loop)
        return True

    def request_release(self, label):
        """Disconnect from a hub and stop trying to reconnect until the user
        clicks 'Forbind' again. Lets another central (e.g. a phone over Web
        Bluetooth) claim the hub."""
        if self._loop is None:
            return False
        if label in self._release_in_progress:
            return False
        self._release_in_progress.add(label)
        asyncio.run_coroutine_threadsafe(self._release_label(label), self._loop)
        return True

    async def _release_label(self, label):
        try:
            self._released.add(label)
            if label == "master":
                name = self.scoreboard_hub
                if self._hub is not None:
                    try:
                        await self._hub.disconnect()
                    except Exception:
                        pass
                    self._hub = None
                self._connected_event.clear()
                self._set_hub_state("master", name, False, "released")
                print("Bridge: master released (phone can now connect)")
            else:
                cfg = self._aux_config.get(label)
                name = cfg[0] if cfg else ""
                for i, (lab, h) in enumerate(list(self._aux_hubs)):
                    if lab == label:
                        try:
                            await h.disconnect()
                        except Exception:
                            pass
                        try:
                            self._aux_hubs.pop(i)
                        except Exception:
                            pass
                        break
                self._set_hub_state(label, name, False, "released")
                print("Bridge: %s released" % label)
        finally:
            self._release_in_progress.discard(label)

    def request_reboot(self, label):
        """Re-run the user program on the hub without re-establishing BLE.
        If label == 'all', reboot every known hub."""
        if self._loop is None:
            return False
        if label == "all":
            with self._hub_states_lock:
                labels = list(self._hub_states.keys())
            for lab in labels:
                if lab not in self._reboot_in_progress:
                    self._reboot_in_progress.add(lab)
                    asyncio.run_coroutine_threadsafe(self._reboot_label(lab), self._loop)
            return True
        if label in self._reboot_in_progress:
            return False
        self._reboot_in_progress.add(label)
        asyncio.run_coroutine_threadsafe(self._reboot_label(label), self._loop)
        return True

    async def _reboot_label(self, label):
        try:
            if label == "master":
                hub = self._hub
                name = self.scoreboard_hub
                script = MASTER_SCRIPT
            else:
                cfg = self._aux_config.get(label)
                if not cfg:
                    print("Bridge: no config for label '%s'" % label)
                    return
                name, script = cfg
                hub = next((h for lab, h in self._aux_hubs if lab == label), None)

            if hub is None:
                # Not currently connected at BLE level; do a full reconnect instead.
                print("Bridge: %s not connected, escalating reboot to reconnect" % label)
                self._reboot_in_progress.discard(label)
                self.request_reconnect(label)
                return

            print("Bridge: rebooting program on %s" % label)
            self._set_hub_state(label, name, False, "rebooting")
            try:
                await hub.stop_user_program()
            except Exception as exc:
                print("Bridge: %s stop_user_program failed: %r" % (label, exc))
            # Give the previous run() task a moment to unwind.
            await asyncio.sleep(0.5)
            if label == "master":
                asyncio.create_task(self._run_program())
            else:
                asyncio.create_task(self._run_aux_program(label, hub, script))
            await asyncio.sleep(0.8)
            self._set_hub_state(label, name, True, None)
            if label == "sled":
                try:
                    self._http.post_json("/api/sled-config/push")
                except Exception:
                    pass
        finally:
            self._reboot_in_progress.discard(label)

    async def _reconnect_label(self, label):
        try:
            from pybricksdev.ble import find_device
            from pybricksdev.connections.pybricks import PybricksHubBLE

            if label == "master":
                name = self.scoreboard_hub
                self._set_hub_state("master", name, False, "reconnecting")
                if self._hub is not None:
                    try:
                        await self._hub.disconnect()
                    except Exception:
                        pass
                    self._hub = None
                self._connected_event.clear()
                try:
                    device = await find_device(name, timeout=self.timeout_seconds)
                    hub = PybricksHubBLE(device)
                    await hub.connect()
                    self._hub = hub
                    hub.stdout_observable.subscribe(self._on_stdout_bytes)
                    asyncio.create_task(self._run_program())
                    await asyncio.sleep(0.5)
                    self._connected_event.set()
                    self._set_hub_state("master", name, True, None)
                    print("Bridge: master reconnected")
                except Exception as exc:
                    self._set_hub_state("master", name, False, exc)
                    print("Bridge: master reconnect failed: %r" % (exc,))
            else:
                cfg = self._aux_config.get(label)
                if not cfg:
                    print("Bridge: no config for label '%s'" % label)
                    return
                name, script_path = cfg
                self._set_hub_state(label, name, False, "reconnecting")
                # Drop existing hub reference
                for i, (lab, h) in enumerate(list(self._aux_hubs)):
                    if lab == label:
                        try:
                            await h.disconnect()
                        except Exception:
                            pass
                        try:
                            self._aux_hubs.pop(i)
                        except Exception:
                            pass
                        break
                try:
                    await self._connect_aux_hub(label, name, script_path,
                                                find_device, PybricksHubBLE)
                    # _connect_aux_hub marks state connected on success
                except Exception as exc:
                    self._set_hub_state(label, name, False, exc)
                    print("Bridge: %s reconnect failed: %r" % (label, exc))
                # Re-push sled config if sled came back
                if label == "sled":
                    try:
                        self._http.post_json("/api/sled-config/push")
                    except Exception:
                        pass
        finally:
            self._reconnect_in_progress.discard(label)

    def _ensure_connected(self):
        if self._loop_thread is not None and self._connected_event.is_set() and not self._connect_error:
            return

        if self._loop_thread is None:
            if not self.scoreboard_hub:
                raise RuntimeError("Missing hub name. Set NGTP_SCOREBOARD_HUB.")
            if self.scoreboard_hub == "DitHubNavn":
                raise RuntimeError(
                    "NGTP_SCOREBOARD_HUB is still the placeholder 'DitHubNavn'."
                )
            if not MASTER_SCRIPT.exists():
                raise RuntimeError("Master script not found: %s" % MASTER_SCRIPT)

            print("Bridge: connecting to hub '%s'" % self.scoreboard_hub)
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._loop_thread.start()
            asyncio.run_coroutine_threadsafe(self._async_setup(), self._loop)

        if not self._connected_event.wait(timeout=self.timeout_seconds + 30):
            raise RuntimeError("Timed out waiting for hub connection")
        if self._connect_error:
            err = self._connect_error
            # Reset so a future command can retry after user fixes the issue.
            self._connect_error = None
            self._connected_event.clear()
            raise RuntimeError("Hub connect error: %r" % err)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _async_setup(self):
        try:
            from pybricksdev.ble import find_device
            from pybricksdev.connections.pybricks import PybricksHubBLE

            print("Bridge: scanning for", self.scoreboard_hub)
            device = await find_device(self.scoreboard_hub, timeout=self.timeout_seconds)
            print("Bridge: device found, connecting...")
            hub = PybricksHubBLE(device)
            await hub.connect()
            self._hub = hub

            # Subscribe to raw hub stdout bytes. We assemble lines ourselves.
            hub.stdout_observable.subscribe(self._on_stdout_bytes)

            # Start the master_broadcaster program (compile + download + run).
            # wait=False: return as soon as the program is started, so we can
            # write to stdin via NUS afterwards.
            print("Bridge: starting", MASTER_SCRIPT.name)
            asyncio.create_task(self._run_program())

            # Give the hub a moment to actually start the program.
            await asyncio.sleep(0.5)

            self._connect_error = None
            self._connected_event.set()
            print("Bridge: hub ready, accepting commands")
            self._set_hub_state("master", self.scoreboard_hub, True, None)

            # Optionally upload+start scripts to additional hubs.
            aux_targets = [
                ("sled", self.sled_hub, SLED_SCRIPT),
                ("display_1", self.display_1_hub, DISPLAY_1_SCRIPT),
                ("display_2", self.display_2_hub, DISPLAY_2_SCRIPT),
                ("display_3", self.display_3_hub, DISPLAY_3_SCRIPT),
            ]
            for label, name, script_path in aux_targets:
                if not name or name == "DitHubNavn":
                    continue
                if not script_path.exists():
                    print("Bridge: %s script missing: %s" % (label, script_path))
                    continue
                self._aux_config[label] = (name, script_path)
                self._set_hub_state(label, name, False, "connecting")
                try:
                    await self._connect_aux_hub(label, name, script_path,
                                                find_device, PybricksHubBLE)
                except Exception as exc:
                    self._set_hub_state(label, name, False, exc)
                    print("Bridge: %s upload failed: %r" % (label, exc))

            # After sled is up, ask server to push current config to it.
            try:
                self._http.post_json("/api/sled-config/push")
                print("Bridge: sled config push requested")
            except Exception as exc:
                print("Bridge: sled config push failed: %r" % (exc,))
        except Exception as exc:
            self._connect_error = exc
            self._connected_event.set()
            print("Bridge: connect failed:", repr(exc))
            self._set_hub_state("master", self.scoreboard_hub, False, exc)
            traceback.print_exc()

    async def _connect_aux_hub(self, label, name, script_path,
                               find_device, PybricksHubBLE):
        print("Bridge: scanning for %s hub '%s'" % (label, name))
        device = await find_device(name, timeout=self.timeout_seconds)
        print("Bridge: %s device found, connecting..." % label)
        hub = PybricksHubBLE(device)
        await hub.connect()
        self._aux_hubs.append((label, hub))

        prefix = "[%s]" % label
        buf = {"data": b""}

        def on_stdout(data, _label=label, _prefix=prefix, _buf=buf):
            try:
                _buf["data"] += bytes(data)
            except Exception:
                return
            while b"\n" in _buf["data"]:
                raw, _buf["data"] = _buf["data"].split(b"\n", 1)
                text = raw.decode("utf-8", errors="replace").rstrip()
                if text:
                    if not DEBUG_HUB_TX and _is_noisy_hub_line(text):
                        continue
                    print(_prefix, text)

        hub.stdout_observable.subscribe(on_stdout)

        print("Bridge: starting %s on %s" % (script_path.name, label))
        asyncio.create_task(self._run_aux_program(label, hub, script_path))
        await asyncio.sleep(0.3)
        self._set_hub_state(label, name, True, None)

    async def _run_aux_program(self, label, hub, script_path):
        try:
            await hub.run(
                str(script_path),
                wait=True,
                print_output=False,
                line_handler=False,
            )
            print("Bridge: %s program ended" % label)
            self._set_hub_state(label, self._aux_config.get(label, ("", ""))[0], False, "program ended")
        except Exception as exc:
            print("Bridge: %s program error: %r" % (label, exc))
            self._set_hub_state(label, self._aux_config.get(label, ("", ""))[0], False, exc)

    async def _run_program(self):
        try:
            await self._hub.run(
                str(MASTER_SCRIPT),
                wait=True,
                print_output=False,
                line_handler=False,
            )
            print("Bridge: hub program ended")
            self._set_hub_state("master", self.scoreboard_hub, False, "program ended")
        except Exception as exc:
            print("Bridge: hub program error:", repr(exc))
            self._set_hub_state("master", self.scoreboard_hub, False, exc)

    def _on_stdout_bytes(self, data):
        try:
            self._stdout_buf += bytes(data)
        except Exception:
            return
        while b"\n" in self._stdout_buf:
            raw, self._stdout_buf = self._stdout_buf.split(b"\n", 1)
            text = raw.decode("utf-8", errors="replace").rstrip()
            if not text:
                continue
            if DEBUG_HUB_TX or not _is_noisy_hub_line(text):
                print("[hub]", text)
            self._handle_hub_line(text)

    # --------------------- Inbound hub line parsing ---------------------

    def _handle_hub_line(self, line):
        parts = line.split()
        if not parts:
            return
        head = parts[0]

        if head == "D" and len(parts) >= 2:
            try:
                distance = int(parts[1])
            except Exception:
                return
            try:
                self._http.post_json("/api/distance/%d" % distance)
            except Exception as exc:
                print("Bridge: distance post failed:", exc)
            return

        if head == "A" and len(parts) >= 2:
            try:
                ack_seq = int(parts[1])
            except Exception:
                return
            self._on_sled_ack(ack_seq)
            return

        if head == "ASSIGN" and len(parts) >= 3:
            try:
                bridge_seq = int(parts[1])
                broadcast_seq = int(parts[2])
            except Exception:
                return
            with self._lock:
                cmd_id = self._pending_bridge.pop(bridge_seq, None)
                if cmd_id is not None:
                    self._pending_sled[broadcast_seq] = cmd_id
            return

    def _on_sled_ack(self, ack_seq):
        with self._lock:
            done = [seq for seq in self._pending_sled if seq <= ack_seq]
            cmd_ids = [self._pending_sled.pop(seq) for seq in done]
        if not cmd_ids:
            return
        with self._ready_acks_lock:
            for cmd_id in cmd_ids:
                self._ready_acks.append(("sled", cmd_id))

    # --------------------- Adapter interface ---------------------

    def drain_pending_acks(self):
        with self._ready_acks_lock:
            acks = self._ready_acks
            self._ready_acks = []
        return acks

    def ack_immediately(self, target):
        return target != "sled"

    def start(self):
        self._ensure_connected()

    def _send_raw(self, line):
        # Short-circuit if we know master is not connected. Avoids 5s timeout
        # and BleakError spam on every queued command.
        with self._hub_states_lock:
            master = self._hub_states.get("master")
        if self._hub is None or self._loop is None or not master or not master.get("connected"):
            raise HubUnavailable("master not connected")
        if not line.endswith("\n"):
            line = line + "\n"
        fut = asyncio.run_coroutine_threadsafe(
            self._hub.write_string(line), self._loop
        )
        try:
            fut.result(timeout=5.0)
        except Exception as exc:
            # Mark master disconnected so subsequent commands short-circuit.
            self._set_hub_state("master", self.scoreboard_hub, False, exc)
            raise HubUnavailable("hub stdin write failed: %r" % exc)

    def _send_score(self, message):
        self._send_raw("S %d" % int(message))

    def _send_sled_command(self, cmd_id, action_int, value_int):
        with self._lock:
            self._cmd_seq += 1
            seq = self._cmd_seq
            self._pending_bridge[seq] = cmd_id
        self._send_raw("C %d %d %d" % (seq, action_int, value_int))
        return seq

    def handle_sled(self, client, command):
        payload = command.get("payload", {})
        action = payload.get("action")
        value = payload.get("value")
        cmd_id = int(command["id"])

        action_int = SLED_ACTION_MAP.get(action)
        if action_int is None:
            raise RuntimeError("Unknown sled action '%s'" % action)

        # Fast-fail if master isn't connected so we don't leak bridge seqs.
        with self._hub_states_lock:
            master = self._hub_states.get("master")
        if self._hub is None or not master or not master.get("connected"):
            raise HubUnavailable("master not connected")

        if action == "set_weight_percent":
            try:
                value_int = int(value)
            except Exception:
                value_int = 0
            if value_int < 0:
                value_int = -1
            elif value_int > 100:
                value_int = 100
        elif action in ("set_ramp_end_m", "set_full_rotations"):
            # Floats encoded as value * 10 (one decimal) over the int link.
            try:
                value_int = int(round(float(value) * 10.0))
            except Exception:
                value_int = 0
            if value_int < 0:
                value_int = 0
        else:
            value_int = 0

        seq = self._send_sled_command(cmd_id, action_int, value_int)
        print("Bridge: sled cmd %d seq=%d action=%s value=%d" % (cmd_id, seq, action, value_int))

    def handle_scoreboard(self, client, command):
        payload = command.get("payload", {})
        action = payload.get("action")
        value = payload.get("value")

        if action == "set_score":
            message = int(value or 0)
        elif action == "full_pull":
            message = 10000
        elif action == "blank":
            message = -1
        elif action == "reset":
            message = 0
        else:
            raise RuntimeError("Unknown scoreboard action '%s'" % action)

        if message < -1:
            message = -1
        if 999 < message < 10000:
            message = 999

        self._send_score(message)


def get_adapter(http_client):
    if MODE == "log":
        return LoggingAdapter()
    if MODE == "pybricks":
        return PybricksExecAdapter(
            scoreboard_hub=PYBRICKS_SCOREBOARD_HUB,
            sled_hub=PYBRICKS_SLED_HUB,
            timeout_seconds=PYBRICKS_TIMEOUT,
            http_client=http_client,
            display_1_hub=PYBRICKS_DISPLAY_1_HUB,
            display_2_hub=PYBRICKS_DISPLAY_2_HUB,
            display_3_hub=PYBRICKS_DISPLAY_3_HUB,
        )
    return LoopbackAdapter()


def process_target(client, adapter, target, last_id):
    cmd = client.get_json("/api/remote/%s/next" % target, {"after_id": last_id})
    if not cmd:
        return last_id

    cmd_id = int(cmd["id"])
    try:
        if target == "sled":
            adapter.handle_sled(client, cmd)
        else:
            adapter.handle_scoreboard(client, cmd)
    except HubUnavailable:
        # Hub not connected; leave the command unacked so it will be
        # retried once the hub is back. Don't return cmd_id (no advance).
        return last_id

    if adapter.ack_immediately(target):
        client.post_json("/api/remote/%s/ack/%d" % (target, cmd_id))
    return cmd_id


def drain_acks(client, adapter):
    for target, cmd_id in adapter.drain_pending_acks():
        try:
            client.post_json("/api/remote/%s/ack/%d" % (target, cmd_id))
        except Exception as exc:
            print("Bridge: deferred ack failed for %s/%d: %r" % (target, cmd_id, exc))


def _status_reporter(client, adapter, stop_event):
    """Periodically push hub status to server, pull reconnect/reboot requests,
    and auto-retry reconnect for hubs that have been offline a while."""
    AUTO_RECONNECT_AFTER_S = 20.0
    while not stop_event.is_set():
        try:
            hubs = adapter.get_hub_states() if hasattr(adapter, "get_hub_states") else []
            try:
                client.post_json("/api/bridge-status", {"hubs": hubs})
            except Exception:
                pass
            try:
                data = client.get_json("/api/bridge-control") or {}
            except Exception:
                data = {}
            for label in data.get("reconnect", []) or []:
                try:
                    if hasattr(adapter, "request_reconnect"):
                        adapter.request_reconnect(label)
                    client.post_json("/api/bridge-control/ack/reconnect/%s" % label)
                    print("Bridge: reconnect requested for '%s'" % label)
                except Exception as exc:
                    print("Bridge: reconnect handling failed for %s: %r" % (label, exc))
            for label in data.get("reboot", []) or []:
                try:
                    if hasattr(adapter, "request_reboot"):
                        adapter.request_reboot(label)
                    client.post_json("/api/bridge-control/ack/reboot/%s" % label)
                    print("Bridge: reboot requested for '%s'" % label)
                except Exception as exc:
                    print("Bridge: reboot handling failed for %s: %r" % (label, exc))
            for label in data.get("release", []) or []:
                try:
                    if hasattr(adapter, "request_release"):
                        adapter.request_release(label)
                    client.post_json("/api/bridge-control/ack/release/%s" % label)
                    print("Bridge: release requested for '%s'" % label)
                except Exception as exc:
                    print("Bridge: release handling failed for %s: %r" % (label, exc))
            # Auto-retry reconnect for stuck-offline aux hubs so the UI pill
            # turns green again once the hub comes back.
            now = time.time()
            last_attempts = getattr(adapter, "_last_auto_reconnect", None)
            released = getattr(adapter, "_released", set())
            for h in hubs:
                label = h.get("label")
                if not label or label == "master":
                    continue
                if label in released:
                    continue
                if h.get("connected"):
                    if last_attempts is not None:
                        last_attempts.pop(label, None)
                    continue
                age = now - float(h.get("ts") or now)
                if age < AUTO_RECONNECT_AFTER_S:
                    continue
                if last_attempts is not None:
                    last = last_attempts.get(label, 0)
                    if now - last < AUTO_RECONNECT_AFTER_S:
                        continue
                    last_attempts[label] = now
                try:
                    if hasattr(adapter, "request_reconnect"):
                        adapter.request_reconnect(label)
                        print("Bridge: auto-reconnect for '%s'" % label)
                except Exception:
                    pass
        except Exception:
            pass
        stop_event.wait(2.0)


def main():
    client = HttpClient(SERVER_URL)
    adapter = get_adapter(client)

    print("Bridge starting")
    print("server:", SERVER_URL)
    print("mode:", MODE)

    stop_event = threading.Event()
    status_thread = threading.Thread(
        target=_status_reporter, args=(client, adapter, stop_event), daemon=True
    )
    status_thread.start()

    try:
        adapter.start()
    except Exception as exc:
        print("Bridge: initial connect failed, will retry on demand: %r" % (exc,))

    sled_id = 0
    scoreboard_id = 0

    while True:
        try:
            sled_id = process_target(client, adapter, "sled", sled_id)
            scoreboard_id = process_target(client, adapter, "scoreboard", scoreboard_id)
            drain_acks(client, adapter)
            time.sleep(POLL_INTERVAL)
        except error.URLError as exc:
            print("Bridge connection error:", exc)
            time.sleep(1.0)
        except KeyboardInterrupt:
            print("Bridge stopped")
            break
        except Exception as exc:
            print("Bridge runtime error [%s]: %r" % (type(exc).__name__, exc))
            traceback.print_exc()
            time.sleep(1.0)


if __name__ == "__main__":
    main()
