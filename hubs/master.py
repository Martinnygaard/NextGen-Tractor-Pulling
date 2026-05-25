from pybricks.parameters import Button, Color
from pybricks.tools import StopWatch, wait

# Debug mode: when True the script will print discovered pybricks attrs
# and potential hub class names to the serial console and exit. Set to
# True, upload to the hub, run it, then inspect the hub REPL output.
DEBUG = False

if DEBUG:
    print("DEBUG: discovering pybricks attributes...")
    try:
        import pybricks as _p
        print('pybricks attrs:', [k for k in dir(_p) if k[0].isupper()])
    except Exception as e:
        print('pybricks import failed:', e)
    try:
        import pybricks.hubs as _hubs
        print('pybricks.hubs attrs:', [k for k in dir(_hubs) if k[0].isupper()])
    except Exception as e:
        print('pybricks.hubs import failed:', e)
    # Try to detect any Hub-like classes
    candidates = ["PrimeHub", "ControlPlusHub", "ControlPlus", "ControlHub", "SpikeHub", "Hub"]
    found = []
    try:
        import pybricks as _p2
        for name in candidates:
            if hasattr(_p2, name):
                found.append(('pybricks', name))
    except Exception:
        pass
    try:
        import pybricks.hubs as _h2
        for name in candidates:
            if hasattr(_h2, name):
                found.append(('pybricks.hubs', name))
    except Exception:
        pass
    print('FOUND:', found)
    raise SystemExit

# Most Control+ builds expose the ControlPlusHub class in pybricks.hubs.
# Auto-detection has failed in this environment, so we use explicit
# MicroPython-compatible import handling and better diagnostics.


def pybricks_import(name, fromlist=None):
    try:
        if fromlist is None:
            return __import__(name)
        return __import__(name, None, None, fromlist)
    except TypeError:
        # Some MicroPython builds do not accept keyword args on __import__.
        try:
            if fromlist is None:
                return __import__(name, None, None, [])
            return __import__(name, None, None, list(fromlist))
        except Exception as e:
            raise


def report_pybricks_attrs():
    print("DEBUG: no hub class found. Inspecting available pybricks names...")
    try:
        import pybricks as _p
        print('pybricks type:', type(_p))
        print('pybricks has __path__:', hasattr(_p, '__path__'))
        print('pybricks __spec__:', getattr(_p, '__spec__', None))
        print('pybricks attrs:', [k for k in dir(_p) if k[0].isupper()])
    except Exception as e:
        print('pybricks import failed:', e)
    try:
        module = pybricks_import('pybricks.hubs', fromlist=['ControlPlusHub'])
        print('pybricks.hubs module:', module)
        print('pybricks.hubs attrs:', [k for k in dir(module) if k[0].isupper()])
    except Exception as e:
        print('pybricks.hubs import failed:', e)


PrimeHub = None
for module_name, class_name in [
    ('pybricks.hubs', 'ControlPlusHub'),
    ('pybricks.hubs', 'PrimeHub'),
    ('pybricks.hubs', 'TechnicHub'),
    ('pybricks.hubs', 'ThisHub'),
    ('pybricks.hubs', 'ControlPlus'),
    ('pybricks.hubs', 'ControlHub'),
    ('pybricks.hubs', 'SpikeHub'),
    ('pybricks.hubs', 'Hub'),
    ('pybricks', 'ControlPlusHub'),
    ('pybricks', 'PrimeHub'),
    ('pybricks', 'TechnicHub'),
    ('pybricks', 'ThisHub'),
    ('pybricks', 'ControlPlus'),
    ('pybricks', 'ControlHub'),
    ('pybricks', 'SpikeHub'),
    ('pybricks', 'Hub'),
]:
    try:
        module = pybricks_import(module_name, fromlist=[class_name])
        if hasattr(module, class_name):
            PrimeHub = getattr(module, class_name)
            break
    except Exception as e:
        print('DEBUG: import', module_name, class_name, 'failed:', e)

if PrimeHub is None:
    report_pybricks_attrs()
    raise ImportError(
        "No compatible hub class found. Check the serial output for available pybricks classes, then edit hubs/master.py manually."
    )

CHANNEL = 1
FULL_PULL_BASE = 10000
FULL_PULL_TRIGGER = 10
FULL_PULL_TEXT = "FULL PULL!!!"
FULL_PULL_FONT_WIDTH = 4
FULL_PULL_DISPLAY_WIDTH = 18
SHORT_PRESS_MS = 400
LONG_PRESS_MS = 1200
IDLE_LOG_INTERVAL_MS = 2000
LOOP_WAIT_MS = 50
SCROLL_STEP_INTERVAL_MS = 200
MASTER_VERSION = "master-v2026-05-19-trigger10"

# Try to keep scroll wrap in sync with display logic; fall back if unavailable.
try:
    from display_logic import TEXT_STRIP, DISPLAY_WIDTH  # type: ignore
    SCROLL_MAX_OFFSET = len(TEXT_STRIP[0]) - DISPLAY_WIDTH
except Exception:
    # Fallback that mirrors display_logic.make_text_strip() spacing rules:
    # - base 1 pixel gap after each character
    # - for consecutive exclamation marks, remove up to two trailing blanks
    #   from the current '!' glyph before applying the 1-pixel gap
    text_unit_width = 0
    for i, ch in enumerate(FULL_PULL_TEXT):
        next_ch = FULL_PULL_TEXT[i + 1] if i + 1 < len(FULL_PULL_TEXT) else None
        glyph_width = FULL_PULL_FONT_WIDTH
        if ch == "!" and next_ch == "!":
            glyph_width -= 2
        gap = 1
        text_unit_width += glyph_width + gap

    strip_len = FULL_PULL_DISPLAY_WIDTH + text_unit_width + FULL_PULL_DISPLAY_WIDTH
    SCROLL_MAX_OFFSET = strip_len - FULL_PULL_DISPLAY_WIDTH

# Control+ and Prime both support BLE broadcast in Pybricks; this code is kept generic.
hub = PrimeHub(broadcast_channel=CHANNEL)

# On many hubs, the center button is the default stop button.
# Disable that behavior so button presses are handled by this script.
try:
    hub.system.set_stop_button(None)
except Exception:
    pass

score = 0
full_pull = False
scroll_offset = 0
button_down = False
press_start_ms = 0
watch = StopWatch()
last_activity_ms = 0
last_idle_log_ms = 0
last_scroll_step_ms = 0

print("BOOT %s trigger=%d" % (MASTER_VERSION, FULL_PULL_TRIGGER))


def broadcast_score():
    if full_pull:
        hub.light.on(Color.GREEN)
        hub.ble.broadcast(FULL_PULL_BASE + scroll_offset)
    else:
        hub.light.on(Color.WHITE)
        hub.ble.broadcast(score)


while True:
    now_ms = watch.time()
    pressed = hub.buttons.pressed()
    if hasattr(Button, "CENTER"):
        center_is_pressed = Button.CENTER in pressed
    else:
        # Fallback for hubs that expose different button enums.
        center_is_pressed = len(pressed) > 0

    if center_is_pressed and not button_down:
        button_down = True
        press_start_ms = now_ms
        last_activity_ms = now_ms

    if not center_is_pressed and button_down:
        duration = now_ms - press_start_ms
        button_down = False
        last_activity_ms = now_ms

        if duration < SHORT_PRESS_MS:
            score = min(999, score + 1)
            full_pull = score >= FULL_PULL_TRIGGER
            if full_pull and scroll_offset > SCROLL_MAX_OFFSET:
                scroll_offset = 0
            if full_pull:
                last_scroll_step_ms = now_ms
        elif duration < LONG_PRESS_MS:
            score = 0
            full_pull = False
            scroll_offset = 0
        else:
            full_pull = True
            last_scroll_step_ms = now_ms

    if now_ms - last_activity_ms >= IDLE_LOG_INTERVAL_MS and now_ms - last_idle_log_ms >= IDLE_LOG_INTERVAL_MS:
        print("IDLE score=%d full_pull=%s scroll=%d" % (score, full_pull, scroll_offset))
        last_idle_log_ms = now_ms

    broadcast_score()

    # Advance scroll after broadcasting so first FULL PULL frame uses offset 0.
    # Use timed stepping so each offset is broadcast multiple times for better
    # synchronization across display hubs.
    if full_pull and now_ms - last_scroll_step_ms >= SCROLL_STEP_INTERVAL_MS:
        scroll_offset += 1
        if scroll_offset > SCROLL_MAX_OFFSET:
            scroll_offset = 0
        last_scroll_step_ms = now_ms

    wait(LOOP_WAIT_MS)
