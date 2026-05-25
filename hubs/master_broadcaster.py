from pybricks.parameters import Color
try:
    from pybricks.parameters import Button
except Exception:
    Button = None
from pybricks.tools import StopWatch, wait

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
        ("pybricks.hubs", "EssentialHub"),
        ("pybricks.hubs", "ControlPlusHub"),
        ("pybricks.hubs", "TechnicHub"),
        ("pybricks.hubs", "ThisHub"),
        ("pybricks", "PrimeHub"),
        ("pybricks", "EssentialHub"),
        ("pybricks", "ControlPlusHub"),
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
    raise ImportError("No compatible hub class found for master_broadcaster.py")

# Channels
# 1: master -> displays + sled  : (score, cmd_seq, cmd_action, cmd_value)
# 2: sled   -> master           : (distance_int, last_ack_seq)
OUT_CHANNEL = 1
SLED_CHANNEL = 2
FULL_PULL_BASE = 10000

LOOP_WAIT_MS = 50
IDLE_LOG_MS = 2000

# Outbound state
score = 0
cmd_seq = 0
cmd_action = 0
cmd_value = 0

# Inbound state (from sled)
last_distance_reported = None
last_ack_reported = None

hub = HubClass(broadcast_channel=OUT_CHANNEL, observe_channels=[SLED_CHANNEL])
watch = StopWatch()


def read_stdin_line():
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


def parse_int(token, default=0):
    try:
        return int(token)
    except Exception:
        return default


def handle_stdin_line(line):
    global score, cmd_seq, cmd_action, cmd_value

    if not line:
        return

    parts = line.split()
    head = parts[0]

    if head == "S" and len(parts) >= 2:
        score = parse_int(parts[1], score)
        print("STDIN S", score)
        return

    if head == "C" and len(parts) >= 4:
        bridge_seq = parse_int(parts[1], 0)
        cmd_action = parse_int(parts[2], 0)
        cmd_value = parse_int(parts[3], 0)
        cmd_seq += 1
        print("ASSIGN %d %d" % (bridge_seq, cmd_seq))
        print("STDIN C", cmd_seq, cmd_action, cmd_value)
        return

    # Back-compat: bare integer is interpreted as score.
    if len(parts) == 1:
        score = parse_int(parts[0], score)
        print("STDIN S(bare)", score)
        return

    print("STDIN ?", line)


# --- Local hub button: short press triggers start_pull (action=1). ---
CMD_START_PULL_LOCAL = 1
_local_btn_last = False


def poll_local_button():
    global cmd_seq, cmd_action, cmd_value, _local_btn_last
    try:
        pressed = hub.buttons.pressed()
    except Exception:
        return
    try:
        is_pressed = len(pressed) > 0
    except Exception:
        is_pressed = bool(pressed)

    if is_pressed and not _local_btn_last:
        cmd_seq += 1
        cmd_action = CMD_START_PULL_LOCAL
        cmd_value = 0
        print("LOCAL START seq=%d" % cmd_seq)
    _local_btn_last = is_pressed


def handle_sled_message(msg):
    global last_distance_reported, last_ack_reported

    if msg is None:
        return

    if isinstance(msg, tuple) and len(msg) >= 2:
        distance = msg[0]
        ack_seq = msg[1]
    else:
        distance = msg
        ack_seq = None

    try:
        distance = int(distance)
    except Exception:
        distance = None

    if distance is not None and distance != last_distance_reported:
        print("D", distance)
        last_distance_reported = distance

    if ack_seq is not None:
        try:
            ack_seq = int(ack_seq)
        except Exception:
            ack_seq = None

    if ack_seq is not None and ack_seq != last_ack_reported and ack_seq > 0:
        print("A", ack_seq)
        last_ack_reported = ack_seq


try:
    hub.system.set_stop_button(None)
except Exception:
    pass

print("BOOT master_broadcaster out=%d sled=%d" % (OUT_CHANNEL, SLED_CHANNEL))
last_log_ms = 0

while True:
    line = read_stdin_line()
    if line is not None:
        handle_stdin_line(line)

    poll_local_button()

    incoming = hub.ble.observe(SLED_CHANNEL)
    handle_sled_message(incoming)

    # Visual: white normally, green for full pull.
    try:
        if score < 0:
            hub.light.off()
        elif score >= FULL_PULL_BASE:
            hub.light.on(Color.GREEN)
        else:
            hub.light.on(Color.WHITE)
    except Exception:
        pass

    hub.ble.broadcast((score, cmd_seq, cmd_action, cmd_value))

    now = watch.time()
    if now - last_log_ms >= IDLE_LOG_MS:
        print("TX score=%d seq=%d act=%d val=%d" % (score, cmd_seq, cmd_action, cmd_value))
        last_log_ms = now

    wait(LOOP_WAIT_MS)
