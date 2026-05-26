print("[boot] inlined entry alive")
# --- inlined from display_logic.py ---
MATRIX_SIZE = 3

# Hardware layout: 6 matrices wide, 3 matrices high (each matrix is 3x3)
DISPLAY_MATRIX_COLS = 6
DISPLAY_MATRIX_ROWS = 3

DISPLAY_WIDTH = DISPLAY_MATRIX_COLS * MATRIX_SIZE  # 18
DISPLAY_HEIGHT = DISPLAY_MATRIX_ROWS * MATRIX_SIZE  # 9

# Per-hub local size: each hub controls 2 matrix columns x 3 matrix rows
MATRIX_COLS = 2
MATRIX_ROWS = 3
LOCAL_WIDTH = MATRIX_COLS * MATRIX_SIZE  # 6
LOCAL_HEIGHT = MATRIX_ROWS * MATRIX_SIZE  # 9
FULL_PULL_BASE = 10000

ON = "1"
OFF = "0"

DIGITS = {
    "0": [
        "1111",
        "1001",
        "1001",
        "1001",
        "1001",
        "1001",
        "1111",
    ],
    "1": [
        "0010",
        "0110",
        "0010",
        "0010",
        "0010",
        "0010",
        "0111",
    ],
    "2": [
        "1111",
        "0001",
        "0001",
        "1111",
        "1000",
        "1000",
        "1111",
    ],
    "3": [
        "1111",
        "0001",
        "0001",
        "1111",
        "0001",
        "0001",
        "1111",
    ],
    "4": [
        "1001",
        "1001",
        "1001",
        "1111",
        "0001",
        "0001",
        "0001",
    ],
    "5": [
        "1111",
        "1000",
        "1000",
        "1111",
        "0001",
        "0001",
        "1111",
    ],
    "6": [
        "1111",
        "1000",
        "1000",
        "1111",
        "1001",
        "1001",
        "1111",
    ],
    "7": [
        "1111",
        "0001",
        "0010",
        "0010",
        "0100",
        "0100",
        "0100",
    ],
    "8": [
        "1111",
        "1001",
        "1001",
        "1111",
        "1001",
        "1001",
        "1111",
    ],
    "9": [
        "1111",
        "1001",
        "1001",
        "1111",
        "0001",
        "0001",
        "1111",
    ],
}
FONT_WIDTH = 4
FONT_HEIGHT = 6

# 4x6 font (selected characters used in "FULL PULL!!!").
FONT = {
    "F": [
        "1111",
        "1000",
        "1110",
        "1000",
        "1000",
        "1000",
    ],
    "U": [
        "1001",
        "1001",
        "1001",
        "1001",
        "1001",
        "0110",
    ],
    "L": [
        "1000",
        "1000",
        "1000",
        "1000",
        "1000",
        "1111",
    ],
    "P": [
        "1110",
        "1001",
        "1001",
        "1110",
        "1000",
        "1000",
    ],
    "!": [
        "0100",
        "0100",
        "0100",
        "0100",
        "0000",
        "0100",
    ],
    " ": ["0000", "0000", "0000", "0000", "0000", "0000"],
}


def blank_canvas(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT):
    return [[OFF] * width for _ in range(height)]


def make_number_canvas(number):
    canvas = blank_canvas(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    text = "%03d" % number
    total_width = 4 + 1 + 4 + 1 + 4
    x = (DISPLAY_WIDTH - total_width) // 2

    digit_height = len(next(iter(DIGITS.values())))
    y_offset = (DISPLAY_HEIGHT - digit_height) // 2

    for char in text:
        bitmap = DIGITS[char]
        for y in range(digit_height):
            for dx in range(4):
                if bitmap[y][dx] == "1":
                    canvas[y + y_offset][x + dx] = ON
        x += 5

    return canvas


def make_text_strip(text):
    strip = [[] for _ in range(FONT_HEIGHT)]
    for y in range(FONT_HEIGHT):
        strip[y].extend([OFF] * DISPLAY_WIDTH)

    for i, char in enumerate(text):
        bitmap = FONT.get(char, FONT[" "])
        for y in range(FONT_HEIGHT):
            strip[y].extend(list(bitmap[y]))

        next_char = text[i + 1] if i + 1 < len(text) else None
        if char == "!" and next_char == "!":
            # Tighten visual spacing for "!!": remove up to two trailing blank
            # columns from the current '!' glyph, then keep a 1-pixel gap.
            removed = 0
            while removed < 2 and all(row and row[-1] == OFF for row in strip):
                for y in range(FONT_HEIGHT):
                    strip[y].pop()
                removed += 1
            gap = 1
        else:
            gap = 1
        for y in range(FONT_HEIGHT):
            strip[y].extend([OFF] * gap)

    for y in range(FONT_HEIGHT):
        strip[y].extend([OFF] * DISPLAY_WIDTH)

    return strip

TEXT_STRIP = make_text_strip("FULL PULL!!!")


def make_full_pull_canvas(offset):
    canvas = blank_canvas(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    max_offset = len(TEXT_STRIP[0]) - DISPLAY_WIDTH
    offset = offset % (max_offset + 1)

    # Center vertically based on font height
    y_offset = (DISPLAY_HEIGHT - FONT_HEIGHT) // 2
    for y in range(FONT_HEIGHT):
        for x in range(DISPLAY_WIDTH):
            canvas[y + y_offset][x] = TEXT_STRIP[y][offset + x]

    return canvas


def crop_local_canvas(global_canvas, global_x_offset):
    local = blank_canvas(LOCAL_WIDTH, LOCAL_HEIGHT)
    for y in range(LOCAL_HEIGHT):
        for x in range(LOCAL_WIDTH):
            local[y][x] = global_canvas[y][x + global_x_offset]
    return local


def rotate_pixels(pixels, rotation):
    if rotation == 0:
        return pixels

    rotated = [OFF] * 9
    for y in range(3):
        for x in range(3):
            old_index = y * 3 + x
            if rotation == 90:
                new_x = 2 - y
                new_y = x
            elif rotation == 180:
                new_x = 2 - x
                new_y = 2 - y
            elif rotation == 270:
                new_x = y
                new_y = 2 - x
            else:
                new_x = x
                new_y = y
            rotated[new_y * 3 + new_x] = pixels[old_index]
    return rotated


def make_test_pattern_canvas(offset=0):
    canvas = blank_canvas(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    for y in range(DISPLAY_HEIGHT):
        for x in range(DISPLAY_WIDTH):
            if (x + y + offset) % 2 == 0:
                canvas[y][x] = ON
    return canvas


def ascii_canvas(canvas):
    return "\n".join(
        "".join("#" if pixel == ON else "." for pixel in row) for row in canvas
    )
# --- inlined from scoreboard_display.py ---
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
    pass  # inlined import removed
except ImportError:
    pass  # inlined import removed

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
    # SMOKE TEST: bypass all hub init and observer setup. Just print at
    # 1 Hz so we can confirm the build pipeline + BLE stdout actually
    # work end to end. If we see "smoketest tick N" in the PWA log,
    # we know the rest of the program (PrimeHub(observe_channels)) is
    # what crashes the hub.
    print("smoketest start idx=", hub_index)
    for i in range(60):
        print("smoketest tick", i)
        wait(1000)
    print("smoketest done")
    return
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

# --- entry display_2.py ---
pass  # inlined import removed


# Display hub 2 controls global matrix columns 3..5.
HUB_INDEX = 1

# Local matrix layout:
# [A][C][E]
# [B][D][F]
# Compensate for 90° CW hardware rotation by rotating matrices 270°.
ROTATIONS = [270, 270, 270, 270, 270, 270]


run_display_hub(HUB_INDEX, ROTATIONS)

