from pybricks.pupdevices import ColorLightMatrix
from pybricks.parameters import Port, Color
from pybricks.tools import wait

def pybricks_import(name, fromlist=None):
    try:
        if fromlist is None:
            return __import__(name)
        return __import__(name, None, None, fromlist)
    except TypeError:
        # Some MicroPython builds do not accept keyword args on __import__.
        if fromlist is None:
            return __import__(name, None, None, [])
        return __import__(name, None, None, list(fromlist))


def try_import_hub():
    candidates = [
        ("pybricks.hubs", "PrimeHub"),
        ("pybricks.hubs", "ControlPlusHub"),
        ("pybricks.hubs", "TechnicHub"),
        ("pybricks.hubs", "ThisHub"),
        ("pybricks.hubs", "ControlPlus"),
        ("pybricks.hubs", "ControlHub"),
        ("pybricks.hubs", "SpikeHub"),
        ("pybricks.hubs", "Hub"),
        ("pybricks", "PrimeHub"),
        ("pybricks", "ControlPlusHub"),
        ("pybricks", "TechnicHub"),
        ("pybricks", "ThisHub"),
        ("pybricks", "ControlPlus"),
        ("pybricks", "ControlHub"),
        ("pybricks", "SpikeHub"),
        ("pybricks", "Hub"),
    ]
    for module_name, class_name in candidates:
        try:
            module = pybricks_import(module_name, fromlist=[class_name])
            if hasattr(module, class_name):
                return getattr(module, class_name)
        except Exception:
            pass
    return None

PrimeHub = try_import_hub()
if PrimeHub is None:
    raise ImportError(
        "No compatible hub class found. Edit hubs/scoreboard_display.py and set PrimeHub manually, e.g. `from pybricks.hubs import ControlPlusHub as PrimeHub`"
    )

try:
    from hubs.display_logic import (
        DISPLAY_WIDTH,
        DISPLAY_HEIGHT,
        LOCAL_WIDTH,
        LOCAL_HEIGHT,
        MATRIX_COLS,
        MATRIX_SIZE,
        FULL_PULL_BASE,
        blank_canvas,
        make_number_canvas,
        make_full_pull_canvas,
        crop_local_canvas,
        rotate_pixels as rotate_pixels_logic,
    )
except ImportError:
    from display_logic import (
        DISPLAY_WIDTH,
        DISPLAY_HEIGHT,
        LOCAL_WIDTH,
        LOCAL_HEIGHT,
        MATRIX_COLS,
        MATRIX_SIZE,
        FULL_PULL_BASE,
        blank_canvas,
        make_number_canvas,
        make_full_pull_canvas,
        crop_local_canvas,
        rotate_pixels as rotate_pixels_logic,
    )

CHANNEL = 1
LAST_MESSAGE_TIMEOUT_MS = 1000

# Version string; CI replaces __NGTP_VERSION__ with the git short SHA at
# build time (see tools/build_programs.py). Shared by all 3 display hubs.
VERSION = "__NGTP_VERSION__"
print("VERSION display", VERSION)
# When True, run a local test loop and ignore BLE broadcasts. Useful
# when the master hub or REPL is not available (e.g., during initial
# hardware bring-up). Set to True on each display hub before upload.
# Temporarily enable only during debug.
TEST_MODE = False
TEST_MESSAGES = [0, 123, 999, -1]  # -1 = blank
TEST_FULL_PULL = True

# When True, run a short diagnostic that lights one matrix at a time so you
# can map physical positions to matrix indices. Useful when the whole image
# appears rotated or mis-arranged.
DIAGNOSTIC_MODE = False

ON = Color.WHITE
OFF = Color.NONE

# Some hardware enumerates attached matrices in column-major order
# (top-left, bottom-left, top-mid, bottom-mid, ...). Set
# `COLUMN_MAJOR = True` when diagnostic mapping shows that order.
COLUMN_MAJOR = True

# Number of matrix rows in the local 3x2 grid (LOCAL_HEIGHT / MATRIX_SIZE)
MATRIX_ROWS = LOCAL_HEIGHT // MATRIX_SIZE


def rotate_pixels(pixels, rotation):
    """Convert string-based rotation result to Color objects."""
    rotated_strings = rotate_pixels_logic(pixels, rotation)
    rotated_colors = []
    for pixel in rotated_strings:
        rotated_colors.append(ON if pixel == "1" else OFF)
    return rotated_colors


def get_matrix_pixels(canvas, matrix_index, rotations):
    if not COLUMN_MAJOR:
        matrix_col = matrix_index % MATRIX_COLS
        matrix_row = matrix_index // MATRIX_COLS
    else:
        matrix_col = matrix_index // MATRIX_ROWS
        matrix_row = matrix_index % MATRIX_ROWS
    start_x = matrix_col * MATRIX_SIZE
    start_y = matrix_row * MATRIX_SIZE
    pixels = []

    for y in range(MATRIX_SIZE):
        for x in range(MATRIX_SIZE):
            if canvas[start_y + y][start_x + x] == "1":
                pixels.append("1")
            else:
                pixels.append("0")

    return rotate_pixels(pixels, rotations[matrix_index])


def show_canvas(matrices, canvas, rotations):
    for i in range(6):
        matrices[i].on(get_matrix_pixels(canvas, i, rotations))


def make_hub_matrices():
    # Default physical wiring (single controller's perspective):
    # Top row:    B A
    # Middle row: D C
    # Bottom row: F E
    # HUB_PHYSICAL_LAYOUT[row][col] where row=0..2 (top->bottom), col=0..1 (left->right)
    HUB_PHYSICAL_LAYOUT = [["B", "A"], ["D", "C"], ["F", "E"]]

    # Build a label -> Port mapping from the physical layout
    label_to_port = {}
    for r in range(len(HUB_PHYSICAL_LAYOUT)):
        for c in range(len(HUB_PHYSICAL_LAYOUT[r])):
            lbl = HUB_PHYSICAL_LAYOUT[r][c]
            label_to_port[lbl] = getattr(Port, lbl)

    # We need to return matrices in the order matching the matrix_index
    # calculation used elsewhere. For column-major enumeration with
    # MATRIX_ROWS = 3 this is: top-left, mid-left, bottom-left,
    # top-right, mid-right, bottom-right.
    logical_order = ["B", "D", "F", "A", "C", "E"]
    ports = [label_to_port[lbl] for lbl in logical_order]
    return [ColorLightMatrix(p) for p in ports]


def run_display_hub(hub_index, rotations):
    # When the PWA flashed + started this program, the BLE radio was
    # still tearing down the GATT link the moment we begin executing.
    # Calling PrimeHub(observe_channels=[...]) before that teardown is
    # complete makes the firmware deadlock a couple of seconds in
    # (program freezes, status light stops rotating). Pause briefly so
    # the central-mode disconnect can settle before we ask the radio to
    # switch into observer mode. Manual hub-button starts pay this same
    # cost but never notice it because nothing was connected to begin
    # with.
    wait(2000)
    hub = PrimeHub(observe_channels=[CHANNEL])
    matrices = make_hub_matrices()
    global_x_offset = hub_index * LOCAL_WIDTH

    last_message = None
    time_since_last = 0

    while True:
        if TEST_MODE:
            if DIAGNOSTIC_MODE:
                # Show one matrix at a time (full ON) so user can observe mapping.
                full_on = [ON] * MATRIX_SIZE * MATRIX_SIZE
                full_off = [OFF] * MATRIX_SIZE * MATRIX_SIZE
                for i in range(6):
                    for j in range(6):
                        matrices[j].on(full_off)
                    matrices[i].on(full_on)
                    wait(500)
                # Continue into the normal TEST_MESSAGES loop afterwards.
            
            # Cycle through test messages and optionally test FULL PULL scroll
            for m in TEST_MESSAGES:
                message = m
                if TEST_FULL_PULL and m >= 0 and m >= 100:
                    # simulate full pull
                    message = FULL_PULL_BASE
                # render current test message
                last_message = message
                time_since_last = 0

                message_to_render = last_message

                if message is None:
                    hub.light.on(Color.ORANGE)
                elif message_to_render < 0:
                    hub.light.on(Color.RED)
                elif message_to_render >= FULL_PULL_BASE:
                    hub.light.on(Color.GREEN)
                else:
                    hub.light.on(Color.WHITE)

                if message_to_render < 0:
                    show_canvas(matrices, blank_canvas(LOCAL_WIDTH, LOCAL_HEIGHT), rotations)
                elif message_to_render >= FULL_PULL_BASE:
                    global_canvas = make_full_pull_canvas(message_to_render - FULL_PULL_BASE)
                    local_canvas = crop_local_canvas(global_canvas, global_x_offset)
                    show_canvas(matrices, local_canvas, rotations)
                else:
                    global_canvas = make_number_canvas(message_to_render)
                    local_canvas = crop_local_canvas(global_canvas, global_x_offset)
                    show_canvas(matrices, local_canvas, rotations)

                wait(500)
            continue

        message = hub.ble.observe(CHANNEL)

        # Master broadcasts a tuple (score, cmd_seq, cmd_action, cmd_value).
        # Displays only care about the score (first element). Plain ints
        # from legacy masters are also accepted. Defensively unwrap nested
        # tuples and coerce to int so a malformed/stale broadcast can never
        # smuggle a tuple into the numeric comparisons below.
        while isinstance(message, tuple) and len(message) > 0:
            message = message[0]
        if message is not None:
            try:
                message = int(message)
            except Exception:
                message = None

        if message is not None:
            last_message = message
            time_since_last = 0
        else:
            time_since_last += 50

        if last_message is not None and time_since_last <= LAST_MESSAGE_TIMEOUT_MS:
            message_to_render = last_message
        else:
            message_to_render = -1

        if message is None:
            hub.light.on(Color.ORANGE)
        elif message_to_render < 0:
            hub.light.on(Color.RED)
        elif message_to_render >= FULL_PULL_BASE:
            hub.light.on(Color.GREEN)
        else:
            hub.light.on(Color.WHITE)

        if message_to_render < 0:
            show_canvas(matrices, blank_canvas(LOCAL_WIDTH, LOCAL_HEIGHT), rotations)
        elif message_to_render >= FULL_PULL_BASE:
            global_canvas = make_full_pull_canvas(message_to_render - FULL_PULL_BASE)
            local_canvas = crop_local_canvas(global_canvas, global_x_offset)
            show_canvas(matrices, local_canvas, rotations)
        else:
            global_canvas = make_number_canvas(message_to_render)
            local_canvas = crop_local_canvas(global_canvas, global_x_offset)
            show_canvas(matrices, local_canvas, rotations)

        wait(50)

