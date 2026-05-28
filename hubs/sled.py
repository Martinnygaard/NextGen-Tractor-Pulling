from pybricks.parameters import Port, Stop, Color, Button
from pybricks.tools import StopWatch, wait
from pybricks.pupdevices import Motor, DCMotor

try:
    from pybricks.pupdevices import Light
except Exception:
    Light = None

# Optional non-blocking stdin reader. Used to accept commands directly from
# the PWA over the Nordic UART (Pybricks stdin) so no master relay is
# needed. Falls back to no-op on firmware that lacks uselect.
try:
    import uselect
except Exception:
    uselect = None

try:
    import usys as sys
except Exception:
    import sys


def pybricks_import(name, fromlist=None):
    try:
        if fromlist is None:
            return __import__(name)
        return __import__(name, None, None, fromlist)
    except TypeError:
        if fromlist is None:
            return __import__(name, None, None, [])
        return __import__(name, None, None, list(fromlist))


def try_import_hub():
    candidates = [
        ("pybricks.hubs", "PrimeHub"),
        ("pybricks.hubs", "TechnicHub"),
        ("pybricks.hubs", "ThisHub"),
        ("pybricks", "PrimeHub"),
        ("pybricks", "TechnicHub"),
        ("pybricks", "ThisHub"),
    ]
    for module_name, class_name in candidates:
        try:
            module = pybricks_import(module_name, fromlist=[class_name])
            if hasattr(module, class_name):
                return getattr(module, class_name)
        except Exception:
            pass
    return None


HubClass = try_import_hub()
if HubClass is None:
    raise ImportError("No compatible hub class found for sled.py")


# Mode constants
MODE_PULL = 1
MODE_PULL_BACK = 2
MODE_FUTURE = 3

# Hardware mapping
DISTANCE_ENCODER_PORT = Port.B
WEIGHT_BOX_PORT = Port.F
DRIVE_MOTOR_PORT = Port.D
RED_LIGHT_PORT = Port.A
GREEN_LIGHT_1_PORT = Port.C
GREEN_LIGHT_2_PORT = Port.E

# Scoreboard channels
# Channel 1: Master broadcasts (score, cmd_seq, cmd_action, cmd_value).
#            Sled observes this channel to receive remote commands.
# Channel 2: Sled broadcasts (distance_int, last_ack_seq) so master can
#            forward both to the server.
SCOREBOARD_CHANNEL = 1
DISTANCE_CHANNEL = 2

# Version string; CI replaces __NGTP_VERSION__ with the git short SHA at
# build time (see tools/build_programs.py).
VERSION = "__NGTP_VERSION__"
print("VERSION sled", VERSION)

# Sled command actions (must match server/bridge_client.py SLED_ACTION_MAP).
CMD_NOOP = 0
CMD_START_PULL = 1
CMD_STOP_PULL = 2
CMD_HOME_WEIGHT = 3
CMD_SET_SIGNAL_RED = 4
CMD_SET_SIGNAL_GREEN = 5
CMD_SET_WEIGHT_PCT = 6
CMD_RESET_DISTANCE = 7
CMD_CLEAR_SIGNAL = 8
CMD_SET_SIGNAL_GREEN_BLINK = 9
CMD_SET_RAMP_END_M = 10
CMD_SET_FULL_ROTATIONS = 11

# Pull logic constants
# REAL_FULL_DISTANCE_M: actual physical track length in real metres
# DISPLAY_FULL_DISTANCE_M: what is shown on the scoreboard ("LEGO metres")
# 6 real metres = 100 LEGO metres
REAL_FULL_DISTANCE_M = 6.0
DISPLAY_FULL_DISTANCE_M = 100.0
DISPLAY_SCALE = DISPLAY_FULL_DISTANCE_M / REAL_FULL_DISTANCE_M  # 16.667
WEIGHT_RAMP_START_M = 5.0    # LEGO metres
WEIGHT_RAMP_END_M = 70.0     # LEGO metres
STOP_DETECT_SECONDS = 5
DISTANCE_TX_INTERVAL_MS = 1000

# --- CONFIGURABLE: encoder rotations for the full 6-metre track ---
# Measured/calculated from gear train (14T -> 22T diff, wheel ø68.7mm).
# Adjust this value if the displayed distance drifts from reality.
FULL_DISTANCE_ROTATIONS = 43.0

REAL_METERS_PER_DEGREE = REAL_FULL_DISTANCE_M / (FULL_DISTANCE_ROTATIONS * 360.0)

# Movement threshold: >= 10 deg/s counts as moving
MOVING_THRESHOLD_DPS = 10.0
# Position-anchor based stop detection: pull ends when the distance encoder
# moves less than STOP_MOTION_TOL_DEG within STOP_DETECT_SECONDS while past
# STOP_DETECT_MIN_DISTANCE_M.
STOP_MOTION_TOL_DEG = 30
STOP_DETECT_MIN_DISTANCE_M = 10.0

# Weight box calibration/drive settings
CALIB_SPEED_DPS = 800
CALIB_FINE_SPEED_DPS = 30
CALIB_DUTY_LIMIT = 60
CALIB_DUTY_STEP = 10
CALIB_MAX_RETRIES = 3
# Acceptable span between mechanical endstops. Loose by design: the actual
# travel depends on gear ratio and build, so we only reject obviously bad
# readings (very short = false stall, very long = sensor wrap/glitch).
CALIB_MIN_TRAVEL_DEG = 1500
CALIB_MAX_TRAVEL_DEG = 12000
CALIB_END_REACH_TOL_DEG = 200
CALIB_BACKOFF_DEG = 80
HOME_OFFSET_DEG = 20
# Pull the 100% target slightly inside the front endstop so the box doesn't
# stall against the mechanical limit (which can trip the Prime hub).
FRONT_OFFSET_DEG = 60
WEIGHT_MOVE_SPEED_DPS = 720

# Timing
MAIN_LOOP_WAIT_MS = 50
RED_READY_MS = 5000
POST_PULL_RED_MS = 5000
DEBUG_STATUS_INTERVAL_MS = 1000

# Green dual-LED alternating blink frequency (Hz).
# 2.0 Hz means each LED completes one full on/off cycle every 0.5 s,
# alternating every 0.25 s.
GREEN_ALT_HZ = 2.0
GREEN_ALT_HALF_PERIOD_MS = int(1000 / (GREEN_ALT_HZ * 2))
if GREEN_ALT_HALF_PERIOD_MS < 1:
    GREEN_ALT_HALF_PERIOD_MS = 1


hub = HubClass(broadcast_channel=DISTANCE_CHANNEL, observe_channels=[SCOREBOARD_CHANNEL])
distance_encoder = Motor(DISTANCE_ENCODER_PORT)
weight_motor = Motor(WEIGHT_BOX_PORT)

# Powered Up LED light unit should bind as Light. Keep fallbacks for firmware
# differences so script remains runnable.
def init_signal_device(port, name):
    if Light is not None:
        try:
            dev = Light(port)
            dev.off()
            return ("light", dev)
        except Exception as e0:
            pass

    try:
        dev = DCMotor(port)
        dev.dc(0)
        return ("dc", dev)
    except Exception as e1:
        try:
            dev = Motor(port)
            dev.stop()
            return ("motor", dev)
        except Exception as e2:
            print("LIGHT", name, "on", port, "NOT FOUND", e1, e2)
            return (None, None)


red_light_type, red_light = init_signal_device(RED_LIGHT_PORT, "RED")
green_light_1_type, green_light_1 = init_signal_device(GREEN_LIGHT_1_PORT, "GREEN_1")
green_light_2_type, green_light_2 = init_signal_device(GREEN_LIGHT_2_PORT, "GREEN_2")

watch = StopWatch()

# Filled by calibrate_weight_box()
weight_front_angle = 0
weight_back_angle = 0
weight_home_angle = 0

# Remote command state. last_command_seq is included in every distance
# broadcast so the master/bridge can ack the originating server command.
last_command_seq = 0

# Manual signal override from remote (None = automatic / state machine owns it)
signal_override_red = None      # True/False or None
signal_override_green = None    # True/False or None
signal_override_green_blink = None  # True/False or None (independent of green)

# Manual weight override (None = automatic ramp)
weight_override_pct = None      # 0..100 or None

# Flags set by remote commands and consumed by the state machine.
flag_start_pull = False
flag_stop_pull = False
flag_home_weight = False
flag_reset_distance = False

# Set True when the sled has been detected stopped at end of a pull.
# Stays True until the next CMD_RESET_DISTANCE (i.e. sled retracted and
# ready for a new pull). While True, the displays show "FULL PULL!!!".
full_pull_signal = False


def mode_name(mode):
    if mode == MODE_PULL:
        return "PULL"
    if mode == MODE_PULL_BACK:
        return "PULL_BACK"
    if mode == MODE_FUTURE:
        return "FUTURE"
    return "UNKNOWN"


def weight_position_percent():
    span = float(weight_front_angle - weight_home_angle)
    if span == 0:
        return 0
    pct = (weight_motor.angle() - weight_home_angle) * 100.0 / span
    if pct < 0:
        pct = 0
    if pct > 100:
        pct = 100
    return int(pct)


debug_pending_events = []
debug_last_state = None
debug_last_emit_ms = -DEBUG_STATUS_INTERVAL_MS


def queue_debug_event(message):
    debug_pending_events.append(message)


# Hold the hub button (Bluetooth/center) for this many ms to stop the
# user program. Fires as soon as the threshold is reached; no need to
# release the button first.
STOP_HOLD_MS = 2000
_stop_btn_press_start_ms = -1


def poll_stop_button():
    """Stop the program when the hub button is held for STOP_HOLD_MS.

    Called from every main loop iteration."""
    global _stop_btn_press_start_ms
    try:
        pressed_set = hub.buttons.pressed()
    except Exception:
        return
    is_pressed = False
    try:
        is_pressed = len(pressed_set) > 0
    except Exception:
        try:
            is_pressed = bool(pressed_set)
        except Exception:
            is_pressed = False

    now_ms = watch.time()
    if is_pressed:
        if _stop_btn_press_start_ms < 0:
            _stop_btn_press_start_ms = now_ms
            try:
                print("BTN press detected:", pressed_set)
            except Exception:
                print("BTN press detected")
        elif now_ms - _stop_btn_press_start_ms >= STOP_HOLD_MS:
            print("STOP: button held %d ms, exiting program" % (now_ms - _stop_btn_press_start_ms))
            try:
                drive_motor.dc(0)
            except Exception:
                pass
            try:
                weight_motor.dc(0)
            except Exception:
                pass
            raise SystemExit
    else:
        if _stop_btn_press_start_ms >= 0:
            print("BTN released after %d ms" % (now_ms - _stop_btn_press_start_ms))
        _stop_btn_press_start_ms = -1


# Local center-button start: short press triggers start_pull from IDLE.
# While a pull is active (`_pull_active`), the same press aborts the pull
# and lets the normal abort path return the weight box home.
_local_start_btn_last = False
_pull_active = False


def poll_local_start_button():
    global _local_start_btn_last, flag_start_pull, flag_stop_pull
    try:
        pressed_set = hub.buttons.pressed()
    except Exception:
        return
    try:
        is_pressed = len(pressed_set) > 0
    except Exception:
        is_pressed = bool(pressed_set)

    if is_pressed and not _local_start_btn_last:
        if _pull_active:
            flag_stop_pull = True
            queue_debug_event("LOCAL stop_pull (button) - aborting pull")
        else:
            flag_start_pull = True
            queue_debug_event("LOCAL start_pull (button)")
    _local_start_btn_last = is_pressed


def flush_debug(mode, distance_m, now_ms):
    global debug_last_state, debug_last_emit_ms

    state = (mode, int(distance_m * 10), weight_position_percent())
    has_update = state != debug_last_state or len(debug_pending_events) > 0
    if not has_update:
        return

    if now_ms - debug_last_emit_ms < DEBUG_STATUS_INTERVAL_MS:
        return

    if len(debug_pending_events) > 0:
        events = " | ".join(debug_pending_events)
        debug_pending_events.clear()
    else:
        events = "-"

    print(
        "DBG mode=%s lane_m=%.1f sled_pct=%d events=%s"
        % (mode_name(mode), distance_m, weight_position_percent(), events)
    )

    debug_last_state = state
    debug_last_emit_ms = now_ms


def broadcast_status(distance_m):
    # Encode display state as bit flags so the displays know when to
    # stay blank instead of mirroring encoder noise from manual moves.
    #   bit 0 (0x1) = full_pull_signal (run scroll/blink animation)
    #   bit 1 (0x2) = visible (a pull is active or full-pull screen)
    # When neither bit is set the displays render MODE_BLANK.
    flags = 0
    if full_pull_signal:
        flags |= 0x1
    if _pull_active or full_pull_signal:
        flags |= 0x2
    try:
        hub.ble.broadcast((int(distance_m), int(last_command_seq), int(flags)))
    except Exception:
        pass


def apply_command(seq, action, value):
    global signal_override_red, signal_override_green, signal_override_green_blink
    global weight_override_pct
    global flag_start_pull, flag_stop_pull, flag_home_weight, flag_reset_distance
    global WEIGHT_RAMP_END_M, FULL_DISTANCE_ROTATIONS, REAL_METERS_PER_DEGREE

    if action == CMD_START_PULL:
        flag_start_pull = True
        queue_debug_event("CMD seq=%d start_pull" % seq)
    elif action == CMD_STOP_PULL:
        flag_stop_pull = True
        queue_debug_event("CMD seq=%d stop_pull" % seq)
    elif action == CMD_HOME_WEIGHT:
        flag_home_weight = True
        queue_debug_event("CMD seq=%d home_weight" % seq)
    elif action == CMD_SET_SIGNAL_RED:
        signal_override_red = True
        signal_override_green = False
        signal_override_green_blink = False
        queue_debug_event("CMD seq=%d signal_red" % seq)
    elif action == CMD_SET_SIGNAL_GREEN:
        signal_override_red = False
        signal_override_green = True
        signal_override_green_blink = False
        queue_debug_event("CMD seq=%d signal_green" % seq)
    elif action == CMD_SET_SIGNAL_GREEN_BLINK:
        signal_override_red = False
        signal_override_green = True
        signal_override_green_blink = True
        queue_debug_event("CMD seq=%d signal_green_blink" % seq)
    elif action == CMD_CLEAR_SIGNAL:
        signal_override_red = None
        signal_override_green = None
        signal_override_green_blink = None
        queue_debug_event("CMD seq=%d clear_signal" % seq)
    elif action == CMD_SET_WEIGHT_PCT:
        if value < 0:
            weight_override_pct = None
            queue_debug_event("CMD seq=%d weight_pct clear" % seq)
        else:
            if value > 100:
                value = 100
            queue_debug_event("CMD seq=%d weight_pct=%d" % (seq, value))
            if _pull_active:
                # During a pull the loop reads weight_override_pct every
                # iteration; store and let it own the motor.
                weight_override_pct = value
            elif weight_home_angle != 0:
                # Outside pull mode: actuate immediately and release control
                # afterwards so the next pull starts from a clean ramp.
                try:
                    span = float(weight_front_angle - weight_home_angle)
                    target = int(weight_home_angle + (value / 100.0) * span)
                    weight_motor.run_target(WEIGHT_MOVE_SPEED_DPS, target, then=Stop.HOLD, wait=False)
                    queue_debug_event("EXEC weight_pct=%d angle=%d" % (value, target))
                except Exception:
                    pass
                weight_override_pct = None
    elif action == CMD_SET_RAMP_END_M:
        # value is LEGO metres * 10 (one decimal)
        new_end = value / 10.0
        if new_end <= WEIGHT_RAMP_START_M:
            new_end = WEIGHT_RAMP_START_M + 1.0
        if new_end > DISPLAY_FULL_DISTANCE_M:
            new_end = DISPLAY_FULL_DISTANCE_M
        WEIGHT_RAMP_END_M = new_end
        queue_debug_event("CMD seq=%d ramp_end_m=%.1f" % (seq, new_end))
    elif action == CMD_SET_FULL_ROTATIONS:
        # value is rotations * 10 (one decimal)
        new_rot = value / 10.0
        if new_rot < 1.0:
            new_rot = 1.0
        FULL_DISTANCE_ROTATIONS = new_rot
        REAL_METERS_PER_DEGREE = REAL_FULL_DISTANCE_M / (FULL_DISTANCE_ROTATIONS * 360.0)
        queue_debug_event("CMD seq=%d full_rotations=%.1f" % (seq, new_rot))
    elif action == CMD_RESET_DISTANCE:
        flag_reset_distance = True
        queue_debug_event("CMD seq=%d reset_distance" % seq)
    else:
        queue_debug_event("CMD seq=%d unknown action=%d value=%d" % (seq, action, value))


def _read_stdin_line():
    """Non-blocking read of one line from stdin, or None if no data.

    The PWA writes Pybricks stdin via the Nordic UART RX char. Lines look
    like ``C <seq> <action> <value>\n`` (same format as the old master
    relay used) so apply_command() can dispatch them unchanged.
    """
    if uselect is None:
        return None
    try:
        poller = uselect.poll()
        poller.register(sys.stdin, uselect.POLLIN)
        events = poller.poll(0)
    except Exception:
        return None
    if not events:
        return None
    try:
        line = sys.stdin.readline()
    except Exception:
        return None
    if not line:
        return None
    return line.strip()


_stdin_seen_seqs = set()


def _handle_stdin_line(line):
    if not line:
        return
    parts = line.split()
    if not parts:
        return
    if parts[0] != "C" or len(parts) < 4:
        print("STDIN ?", line)
        return
    try:
        seq = int(parts[1])
        action = int(parts[2])
        value = int(parts[3])
    except Exception:
        print("STDIN parse error:", line)
        return
    # Deduplicate retransmits without rejecting low seqs on reconnect.
    if seq in _stdin_seen_seqs:
        return
    _stdin_seen_seqs.add(seq)
    # Cap memory of the dedup set.
    if len(_stdin_seen_seqs) > 256:
        try:
            _stdin_seen_seqs.clear()
            _stdin_seen_seqs.add(seq)
        except Exception:
            pass
    print("STDIN C", seq, action, value)
    apply_command(seq, action, value)


def poll_commands():
    """Read latest broadcast on SCOREBOARD_CHANNEL and dispatch new commands.

    Master broadcasts (score, cmd_seq, cmd_action, cmd_value) continuously.
    A command is "new" when cmd_seq is greater than last_command_seq.
    Called from every state machine loop iteration."""
    global last_command_seq, flag_reset_distance, flag_home_weight
    global full_pull_signal

    poll_stop_button()
    poll_local_start_button()

    # Accept commands directly from the PWA via stdin (NUS write).
    # Drain anything pending so a burst of writes is applied in one loop.
    while True:
        sline = _read_stdin_line()
        if sline is None:
            break
        _handle_stdin_line(sline)

    try:
        msg = hub.ble.observe(SCOREBOARD_CHANNEL)
    except Exception:
        msg = None

    if isinstance(msg, tuple) and len(msg) >= 4:
        seq = int(msg[1])
        action = int(msg[2])
        value = int(msg[3])
        if seq > last_command_seq and action != CMD_NOOP:
            apply_command(seq, action, value)
            last_command_seq = seq

    # Handle non-state-machine commands here so they work from any loop.
    if flag_reset_distance:
        try:
            distance_encoder.reset_angle(0)
            queue_debug_event("EXEC reset_distance")
        except Exception:
            pass
        # Clearing distance also clears any pending FULL PULL state so the
        # displays return to 0 once the sled has been retracted.
        if full_pull_signal:
            full_pull_signal = False
            queue_debug_event("EXEC clear_full_pull")
        flag_reset_distance = False

    if flag_home_weight and weight_home_angle != 0:
        try:
            weight_motor.run_target(WEIGHT_MOVE_SPEED_DPS, weight_home_angle, then=Stop.HOLD, wait=False)
            queue_debug_event("EXEC home_weight")
        except Exception:
            pass
        flag_home_weight = False


def set_signal(red_on, green_on, green_blink=False):
    # Manual overrides from remote commands take precedence over state machine.
    if signal_override_red is not None:
        red_on = signal_override_red
    if signal_override_green is not None:
        green_on = signal_override_green
    if signal_override_green_blink is not None:
        green_blink = signal_override_green_blink

    any_external = False

    # Solid both greens during pull. After passing the full-pull distance
    # (green_blink=True) alternate the two green LEDs in anti-phase at 2 Hz.
    if green_on and green_blink:
        phase = (watch.time() // GREEN_ALT_HALF_PERIOD_MS) % 2
        green_1_on = phase == 0
        green_2_on = not green_1_on
    elif green_on:
        green_1_on = True
        green_2_on = True
    else:
        green_1_on = False
        green_2_on = False

    if red_light is not None:
        any_external = True
        if red_light_type == "light":
            if red_on:
                red_light.on(100)
            else:
                red_light.off()
        elif red_light_type == "dc":
            red_light.dc(100 if red_on else 0)
        else:
            if red_on:
                red_light.run(600)
            else:
                red_light.stop()
    for green_light_type, green_light, this_green_on in [
        (green_light_1_type, green_light_1, green_1_on),
        (green_light_2_type, green_light_2, green_2_on),
    ]:
        if green_light is None:
            continue

        any_external = True
        if green_light_type == "light":
            if this_green_on:
                green_light.on(100)
            else:
                green_light.off()
        elif green_light_type == "dc":
            green_light.dc(100 if this_green_on else 0)
        else:
            if this_green_on:
                green_light.run(600)
            else:
                green_light.stop()

    # Fallback: if no external signal lights are present on E/F,
    # use the hub's built-in status light.
    if not any_external:
        try:
            if red_on and not green_on:
                hub.light.on(Color.RED)
            elif green_on and not red_on:
                hub.light.on(Color.GREEN)
            elif red_on and green_on:
                hub.light.on(Color.ORANGE)
            else:
                hub.light.off()
        except Exception:
            pass


def run_until_stalled_safe(motor, speed, duty_limit):
    try:
        motor.run_until_stalled(speed, then=Stop.HOLD, duty_limit=duty_limit)
    except TypeError:
        motor.run_until_stalled(speed, then=Stop.HOLD)


def seek_endstop(direction, duty_limit):
    coarse_speed = CALIB_SPEED_DPS if direction > 0 else -CALIB_SPEED_DPS
    fine_speed = CALIB_FINE_SPEED_DPS if direction > 0 else -CALIB_FINE_SPEED_DPS

    run_until_stalled_safe(weight_motor, coarse_speed, duty_limit)
    coarse = weight_motor.angle()

    backoff_target = coarse - direction * CALIB_BACKOFF_DEG
    weight_motor.run_target(120, backoff_target, then=Stop.HOLD, wait=True)
    wait(150)

    run_until_stalled_safe(weight_motor, fine_speed, duty_limit)
    return weight_motor.angle()


def calibrate_weight_box():
    global weight_front_angle, weight_back_angle, weight_home_angle

    end_1 = 0
    end_2 = 0
    duty_limit = CALIB_DUTY_LIMIT
    best_travel = 0
    best_end_1 = 0
    best_end_2 = 0

    for attempt in range(CALIB_MAX_RETRIES):
        end_1 = seek_endstop(1, duty_limit)
        wait(300)
        end_2 = seek_endstop(-1, duty_limit)
        wait(300)

        travel = abs(end_1 - end_2)
        print("CALIB attempt=%d end_1=%d end_2=%d travel=%d duty=%d (accept %d..%d)" % (
            attempt + 1, end_1, end_2, travel, duty_limit,
            CALIB_MIN_TRAVEL_DEG, CALIB_MAX_TRAVEL_DEG,
        ))
        if travel > best_travel:
            best_travel = travel
            best_end_1 = end_1
            best_end_2 = end_2

        if CALIB_MIN_TRAVEL_DEG <= travel <= CALIB_MAX_TRAVEL_DEG:
            break

        # False stall likely happened in a sticky mid-zone. Push through a bit
        # in both directions before retrying with more duty.
        try:
            weight_motor.run_angle(220, 240, then=Stop.HOLD, wait=True)
            wait(150)
            weight_motor.run_angle(220, -240, then=Stop.HOLD, wait=True)
        except Exception:
            pass

        duty_limit += CALIB_DUTY_STEP

    if best_travel > abs(end_1 - end_2):
        end_1 = best_end_1
        end_2 = best_end_2

    travel = abs(end_1 - end_2)
    if travel < CALIB_MIN_TRAVEL_DEG or travel > CALIB_MAX_TRAVEL_DEG:
        raise RuntimeError(
            "Calibration failed: invalid travel span (travel=%d, expected %d..%d)."
            % (travel, CALIB_MIN_TRAVEL_DEG, CALIB_MAX_TRAVEL_DEG)
        )

    # Determine back/front from measured limits so direction can be swapped
    # in hardware without breaking calibration.
    weight_back_angle = min(end_1, end_2)
    weight_front_angle = max(end_1, end_2) - FRONT_OFFSET_DEG

    # Park slightly away from the back stop to reduce mechanical stress.
    weight_home_angle = weight_back_angle + HOME_OFFSET_DEG

    if not (weight_back_angle < weight_home_angle < weight_front_angle):
        raise RuntimeError(
            "Calibration failed: computed home outside endstops (back=%d home=%d front=%d)."
            % (weight_back_angle, weight_home_angle, weight_front_angle)
        )

    weight_motor.run_target(WEIGHT_MOVE_SPEED_DPS, weight_home_angle, then=Stop.HOLD, wait=True)



def ensure_pull_start_state():
    # Pre-check: weight at home and distance reset to 0 m.
    weight_motor.run_target(WEIGHT_MOVE_SPEED_DPS, weight_home_angle, then=Stop.HOLD, wait=True)
    distance_encoder.reset_angle(0)



def distance_m_from_encoder():
    real_m = -distance_encoder.angle() * REAL_METERS_PER_DEGREE
    if real_m < 0:
        real_m = 0.0
    # Note: no upper cap. The displays can render up to 3-digit numbers,
    # so let the actual score through even if the tractor pulls past the
    # calibrated full-pull distance.
    return real_m * DISPLAY_SCALE  # convert to LEGO metres



def weight_target_for_distance(distance_m):
    if distance_m <= WEIGHT_RAMP_START_M:
        return weight_home_angle
    if distance_m >= WEIGHT_RAMP_END_M:
        return weight_front_angle

    frac = (distance_m - WEIGHT_RAMP_START_M) / (WEIGHT_RAMP_END_M - WEIGHT_RAMP_START_M)
    return int(weight_home_angle + frac * (weight_front_angle - weight_home_angle))



def run_pull_mode():
    global debug_last_state, flag_stop_pull, flag_start_pull, _pull_active
    global full_pull_signal

    flag_start_pull = False
    flag_stop_pull = False
    _pull_active = True
    # Clear any leftover FULL PULL from the previous run so the displays
    # switch back to live distance for this new pull.
    if full_pull_signal:
        full_pull_signal = False
        queue_debug_event("EXEC clear_full_pull (new pull)")
    ensure_pull_start_state()
    debug_pending_events.clear()
    debug_last_state = None

    # Red for 5 seconds while tractor gets ready. The displays should
    # show 0 during this phase even if the tractor is creeping on the
    # encoder; the real score doesn't start counting until green.
    set_signal(True, False)
    queue_debug_event("STATE READY (RED) - waiting for tractor")
    ready_start = watch.time()
    while watch.time() - ready_start < RED_READY_MS:
        poll_commands()
        if flag_stop_pull:
            queue_debug_event("STATE ABORT during READY")
            flag_stop_pull = False
            flush_debug(MODE_PULL, distance_m_from_encoder(), watch.time())
            return
        set_signal(True, False)
        broadcast_status(0)
        flush_debug(MODE_PULL, 0, watch.time())
        wait(MAIN_LOOP_WAIT_MS)

    # Green means pull can start. Zero the encoder NOW so the score on
    # the displays starts from 0 the instant the tractor sees green.
    try:
        distance_encoder.reset_angle(0)
        queue_debug_event("EXEC reset_distance (GREEN start)")
    except Exception:
        pass
    set_signal(False, True)
    queue_debug_event("STATE PULL_START (GREEN) - tractor can begin pull")

    last_tx_ms = -DISTANCE_TX_INTERVAL_MS
    last_speed_sample_ms = watch.time()
    last_angle = distance_encoder.angle()
    last_motion_ms = watch.time()
    stop_anchor_angle = distance_encoder.angle()
    stop_anchor_ms = watch.time()

    # Track weight box milestones for state transitions
    weight_started = False
    weight_at_front = False

    while True:
        poll_commands()
        if flag_stop_pull:
            queue_debug_event("STATE ABORT during PULL")
            flag_stop_pull = False
            break

        now_ms = watch.time()
        angle = distance_encoder.angle()

        dt_ms = now_ms - last_speed_sample_ms
        if dt_ms <= 0:
            dt_ms = 1
        speed_dps = abs(angle - last_angle) * 1000.0 / dt_ms

        if speed_dps >= MOVING_THRESHOLD_DPS:
            last_motion_ms = now_ms

        # Position-anchor: reset whenever we've moved beyond the tolerance.
        if abs(angle - stop_anchor_angle) > STOP_MOTION_TOL_DEG:
            stop_anchor_angle = angle
            stop_anchor_ms = now_ms

        distance_m = distance_m_from_encoder()

        # Distance + ack to scoreboard once per second.
        if now_ms - last_tx_ms >= DISTANCE_TX_INTERVAL_MS:
            broadcast_status(distance_m)
            last_tx_ms = now_ms

        # Weight box profile: manual override wins, otherwise ramp by distance.
        if weight_override_pct is not None:
            span = float(weight_front_angle - weight_home_angle)
            target = int(weight_home_angle + (weight_override_pct / 100.0) * span)
        else:
            target = weight_target_for_distance(distance_m)
        weight_motor.run_target(WEIGHT_MOVE_SPEED_DPS, target, then=Stop.HOLD, wait=False)

        # Re-render signal so green LEDs keep alternating.
        # Solid green during pull; blink only after passing full-pull distance.
        passed_full = distance_m >= DISPLAY_FULL_DISTANCE_M
        set_signal(False, True, green_blink=passed_full)

        if distance_m >= WEIGHT_RAMP_START_M and not weight_started:
            weight_started = True
            queue_debug_event("STATE WEIGHT_MOVING - weight box starting movement at %.1f m" % distance_m)

        if distance_m >= WEIGHT_RAMP_END_M and not weight_at_front:
            weight_at_front = True
            queue_debug_event("STATE WEIGHT_FRONT - weight box at maximum position at %.1f m" % distance_m)

        if (now_ms - stop_anchor_ms) >= STOP_DETECT_SECONDS * 1000 and distance_m >= STOP_DETECT_MIN_DISTANCE_M:
            queue_debug_event("STATE PULL_END - sled stopped for %d seconds at %.1f m" % (STOP_DETECT_SECONDS, distance_m))
            full_pull_signal = True
            queue_debug_event("EXEC set_full_pull")
            broadcast_status(distance_m)
            flush_debug(MODE_PULL, distance_m, now_ms)
            break

        flush_debug(MODE_PULL, distance_m, now_ms)

        last_speed_sample_ms = now_ms
        last_angle = angle
        wait(MAIN_LOOP_WAIT_MS)

    # Back to red for 5 seconds after finished pull.
    set_signal(True, False)
    queue_debug_event("STATE POST_PULL (RED) - cooling down")
    post_start = watch.time()
    while watch.time() - post_start < POST_PULL_RED_MS:
        poll_commands()
        set_signal(True, False)
        broadcast_status(distance_m_from_encoder())
        flush_debug(MODE_PULL, distance_m_from_encoder(), watch.time())
        wait(MAIN_LOOP_WAIT_MS)

    # Bring weight box back home.
    queue_debug_event("STATE RETURN_HOME - weight box returning to home")
    flush_debug(MODE_PULL, distance_m_from_encoder(), watch.time())
    weight_motor.run_target(WEIGHT_MOVE_SPEED_DPS, weight_home_angle, then=Stop.HOLD, wait=True)
    queue_debug_event("STATE IDLE - ready for next pull")
    flush_debug(MODE_PULL, distance_m_from_encoder(), watch.time())
    _pull_active = False



def run_pull_back_mode():
    # Placeholder for mode 2.
    queue_debug_event("STATE PULL_BACK - placeholder mode")
    flush_debug(MODE_PULL_BACK, distance_m_from_encoder(), watch.time())
    set_signal(True, False)
    wait(500)



def run_idle():
    """Idle loop: poll commands, broadcast status, keep weight at home.

    Exits when start_pull is requested via remote command."""
    global flag_start_pull

    queue_debug_event("STATE IDLE - waiting for start_pull")
    while True:
        poll_commands()
        if flag_start_pull:
            flag_start_pull = False
            return

        set_signal(False, False)
        broadcast_status(distance_m_from_encoder())
        flush_debug(MODE_PULL, distance_m_from_encoder(), watch.time())
        wait(MAIN_LOOP_WAIT_MS)


def main():
    try:
        hub.system.set_stop_button(None)
    except Exception:
        pass

    calibrate_weight_box()

    # Sync button state so a press held during calibration doesn't
    # immediately trigger a pull when IDLE starts polling.
    global _local_start_btn_last, _stop_btn_press_start_ms
    try:
        _local_start_btn_last = len(hub.buttons.pressed()) > 0
    except Exception:
        _local_start_btn_last = False
    _stop_btn_press_start_ms = -1

    while True:
        run_idle()
        run_pull_mode()


main()
