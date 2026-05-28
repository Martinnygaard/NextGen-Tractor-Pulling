# display_common.py
#
# Cooperative driver for the 9x18 LED matrix scoreboard.
# Used by display_1.py, display_2.py, display_3.py.
#
# Design notes:
#   * PrimeHub() is constructed by boot() BEFORE the first print() to
#     avoid the BLE-stdout race that hung the old auto-start path. Each
#     wrapper MUST call boot(...) on its first line.
#   * Displays observe SLED_CHANNEL directly. The sled (hubs/sled.py)
#     broadcasts (distance_m_int, ack_seq, full_pull_flag) on that
#     channel. No master hub is required: the sled IS the source of
#     truth, and all three displays decode the same packet so the 9x18
#     canvas stays consistent.
#   * Anchor model for scroll animations (full-pull text): we re-anchor
#     when the decoded MODE changes, then advance the frame counter
#     from each display's local StopWatch. Because all displays receive
#     the mode transition within ~ms of each other, scroll stays
#     visually aligned across the seam without further broadcasts.
#   * Explicit port_grid (rows top->bottom, cols left->right) per hub.
#   * Per-panel rotation as a plain int (0/90/180/270).

from pybricks.hubs import PrimeHub
from pybricks.pupdevices import ColorLightMatrix
from pybricks.parameters import Port, Color
from pybricks.tools import wait, StopWatch


# --- Boot -------------------------------------------------------------------
# Channel the sled broadcasts on. MUST match hubs/sled.py DISTANCE_CHANNEL.
SLED_CHANNEL = 2

# Wall-time per 1 pixel of scroll. Only matters for animated modes.
SCROLL_STEP_MS = 100

# How often the render loop refreshes the panels.
FRAME_MS = 33

_HUB = None


def boot(broadcast_channel=None, observe_channels=None):
    """Construct PrimeHub() and store it. Must be called BEFORE any print().

    broadcast_channel: int or None - channel this hub broadcasts on.
    observe_channels:  iterable of ints or None - channels this hub listens on.
    """
    global _HUB
    kwargs = {}
    if broadcast_channel is not None:
        kwargs["broadcast_channel"] = broadcast_channel
    if observe_channels:
        kwargs["observe_channels"] = list(observe_channels)
    _HUB = PrimeHub(**kwargs)
    _HUB.light.on(Color.GREEN)
    return _HUB

print("display_common boot")


# --- Geometry ---------------------------------------------------------------
MATRIX_SIZE = 3           # each ColorLightMatrix panel is 3x3 px
GLOBAL_W = 18             # full scoreboard: 18 px wide
GLOBAL_H = 9              # 9 px tall
LOCAL_W = 6               # each hub drives 2 panel-cols = 6 px
LOCAL_H = 9               # each hub drives 3 panel-rows = 9 px
PANEL_ROWS = 3            # 3 rows of panels per hub
PANEL_COLS = 2            # 2 cols of panels per hub


# --- 4x7 digit font (same shapes as the old scoreboard) ---------------------
DIGITS = {
    "0": ["1111", "1001", "1001", "1001", "1001", "1001", "1111"],
    "1": ["0010", "0110", "0010", "0010", "0010", "0010", "0111"],
    "2": ["1111", "0001", "0001", "1111", "1000", "1000", "1111"],
    "3": ["1111", "0001", "0001", "1111", "0001", "0001", "1111"],
    "4": ["1001", "1001", "1001", "1111", "0001", "0001", "0001"],
    "5": ["1111", "1000", "1000", "1111", "0001", "0001", "1111"],
    "6": ["1111", "1000", "1000", "1111", "1001", "1001", "1111"],
    "7": ["1111", "0001", "0010", "0010", "0100", "0100", "0100"],
    "8": ["1111", "1001", "1001", "1111", "1001", "1001", "1111"],
    "9": ["1111", "1001", "1001", "1111", "0001", "0001", "1111"],
}
# 4x7 letters used by full-pull scroll. Same height as DIGITS so they
# share the marquee builder.
LETTERS = {
    "F": ["1111", "1000", "1110", "1000", "1000", "1000", "0000"],
    "U": ["1001", "1001", "1001", "1001", "1001", "1001", "0110"],
    "L": ["1000", "1000", "1000", "1000", "1000", "1000", "1111"],
    "P": ["1110", "1001", "1001", "1110", "1000", "1000", "0000"],
    "!": ["0100", "0100", "0100", "0100", "0000", "0100", "0000"],
    " ": ["0000", "0000", "0000", "0000", "0000", "0000", "0000"],
}
GLYPHS = {}
GLYPHS.update(DIGITS)
GLYPHS.update(LETTERS)

DIGIT_W = 4
DIGIT_H = 7
DIGIT_GAP = 1

ON = Color.WHITE
OFF = Color.NONE


# --- Broadcast protocol -----------------------------------------------------
# Sled broadcasts (distance_int, ack_seq, full_pull_flag) on SLED_CHANNEL.
# Displays decode it into one of these render modes:
#   MODE_BLANK     - no packet seen yet (or sled silent) -> dark canvas
#   MODE_NUMBER    - render `distance_int` centered on the 18-wide canvas
#   MODE_FULL_PULL - scrolling "FULL PULL!!!" marquee
MODE_BLANK = 0
MODE_NUMBER = 1
MODE_FULL_PULL = 2


# --- Rendering --------------------------------------------------------------
def render_number(n):
    """Return a GLOBAL_H x GLOBAL_W grid of bools for an integer 1..999.

    The digits are centered horizontally on the full 18-px canvas. Useful
    for the eventual scoreboard rendering, but NOT a good test pattern: a
    single-digit number only lights pixels on the middle hub.
    """
    canvas = [[False] * GLOBAL_W for _ in range(GLOBAL_H)]
    text = str(n)
    total_w = len(text) * DIGIT_W + (len(text) - 1) * DIGIT_GAP
    x = (GLOBAL_W - total_w) // 2
    y0 = (GLOBAL_H - DIGIT_H) // 2  # = 1
    for ch in text:
        bmp = DIGITS[ch]
        for dy in range(DIGIT_H):
            row = bmp[dy]
            for dx in range(DIGIT_W):
                if row[dx] == "1":
                    canvas[y0 + dy][x + dx] = True
        x += DIGIT_W + DIGIT_GAP
    return canvas


def build_text_strip(text, glyphs=GLYPHS, char_gap=DIGIT_GAP, leading=GLOBAL_W, trailing=GLOBAL_W):
    """Build a wide bitmap of `text` rendered with `glyphs`.

    Output is a list of DIGIT_H rows of bools. `char_gap` blank pixels
    between consecutive characters. `leading`/`trailing` blank columns
    pad the start/end so a scroll begins and ends cleanly off-screen.
    """
    strip = [[] for _ in range(DIGIT_H)]

    def pad(width):
        for y in range(DIGIT_H):
            strip[y].extend([False] * width)

    pad(leading)
    for i, ch in enumerate(text):
        bmp = glyphs[ch]
        for y in range(DIGIT_H):
            row = bmp[y]
            for dx in range(DIGIT_W):
                strip[y].append(row[dx] == "1")
        if i < len(text) - 1:
            pad(char_gap)
    pad(trailing)
    return strip


def _build_test_marquee():
    """Pre-build the 1..100 marquee used in test mode."""
    parts = []
    for n in range(1, 101):
        if parts:
            parts.append(" ")  # single space between numbers
        parts.extend(str(n))
    return build_text_strip("".join(parts))


def _build_full_pull_strip():
    return build_text_strip("FULL PULL!!!")


def render_scroll_frame(strip, offset):
    """Crop a GLOBAL_W-wide window of `strip` at horizontal `offset`."""
    canvas = [[False] * GLOBAL_W for _ in range(GLOBAL_H)]
    y0 = (GLOBAL_H - DIGIT_H) // 2
    strip_w = len(strip[0])
    if strip_w == 0:
        return canvas
    for x in range(GLOBAL_W):
        sx = (offset + x) % strip_w
        for y in range(DIGIT_H):
            canvas[y0 + y][x] = strip[y][sx]
    return canvas


def local_slice(canvas, hub_index):
    """Return the LOCAL_H x LOCAL_W slice of the global canvas for this hub."""
    x_off = hub_index * LOCAL_W
    return [row[x_off:x_off + LOCAL_W] for row in canvas]


# --- Matrix driver ----------------------------------------------------------
class HubDisplay:
    """Drives 6 ColorLightMatrix panels arranged 3 rows x 2 cols.

    port_grid is a PANEL_ROWS x PANEL_COLS list of port label strings
    ("A".."F") describing the physical layout, top-to-bottom and
    left-to-right as seen by the operator.

    Example::

        port_grid = [["B", "A"],
                     ["D", "C"],
                     ["F", "E"]]

    rotation is applied to EACH 3x3 sub-image and is one of 0/90/180/270.
    """

    def __init__(self, port_grid, rotation=0):
        if len(port_grid) != PANEL_ROWS:
            raise ValueError("port_grid must have 3 rows")
        for row in port_grid:
            if len(row) != PANEL_COLS:
                raise ValueError("port_grid rows must have 2 cols")
        self._rotation = rotation % 360
        self._panels = []
        for row in port_grid:
            built = []
            for label in row:
                built.append(ColorLightMatrix(getattr(Port, label)))
            self._panels.append(built)

    def _rotate(self, pixels):
        rot = self._rotation
        if rot == 0:
            return pixels
        out = [OFF] * 9
        for y in range(3):
            for x in range(3):
                v = pixels[y * 3 + x]
                if rot == 90:
                    nx, ny = 2 - y, x
                elif rot == 180:
                    nx, ny = 2 - x, 2 - y
                else:  # 270
                    nx, ny = y, 2 - x
                out[ny * 3 + nx] = v
        return out

    def show(self, local_canvas):
        """Push a LOCAL_H x LOCAL_W bool canvas to the 6 panels."""
        for pr in range(PANEL_ROWS):
            y0 = pr * MATRIX_SIZE
            for pc in range(PANEL_COLS):
                x0 = pc * MATRIX_SIZE
                pixels = []
                for dy in range(MATRIX_SIZE):
                    row = local_canvas[y0 + dy]
                    for dx in range(MATRIX_SIZE):
                        pixels.append(ON if row[x0 + dx] else OFF)
                self._panels[pr][pc].on(self._rotate(pixels))

    def clear(self):
        blank = [OFF] * 9
        for row in self._panels:
            for p in row:
                p.on(blank)


# --- Run loop ---------------------------------------------------------------
def _decode_sled(val):
    """Decode a packet observed on SLED_CHANNEL.

    Sled format: (distance_int, ack_seq, full_pull_flag).
    Returns (mode, value) or None if undecodable.
    """
    if val is None:
        return None
    if isinstance(val, tuple) and len(val) >= 3:
        try:
            distance = int(val[0])
            flags = int(val[2])
        except Exception:
            return None
        full_pull = (flags & 0x1) != 0
        visible = (flags & 0x2) != 0
        if full_pull:
            # Carry the distance through so the FULL PULL animation can
            # blink the actual result number on the displays.
            return (MODE_FULL_PULL, distance)
        if not visible:
            return (MODE_BLANK, 0)
        return (MODE_NUMBER, distance)
    # Bare int -> treat as distance (handy for quick test broadcasts).
    try:
        return (MODE_NUMBER, int(val))
    except Exception:
        return None


def run_display(hub_index, port_grid, rotation=270):
    """Render whatever the sled is broadcasting on SLED_CHANNEL.

    Anchors the scroll frame whenever the decoded MODE changes, so a
    fresh FULL_PULL transition starts from offset 0 on every display at
    (roughly) the same wall-clock instant. Within a mode the frame
    counter advances from each display's local StopWatch.

    boot(...) MUST have been called first with observe_channels=[SLED_CHANNEL].
    """
    if hub_index not in (0, 1, 2):
        raise ValueError("hub_index must be 0, 1, or 2")
    if _HUB is None:
        raise RuntimeError("call boot(...) before run_display(...)")
    print("display run hub_index=", hub_index,
          "rotation=", rotation, "sled_ch=", SLED_CHANNEL)

    display = HubDisplay(port_grid, rotation)
    _HUB.light.on(Color.WHITE)

    full_strip = _build_full_pull_strip()
    full_w = len(full_strip[0])
    blank = [[False] * GLOBAL_W for _ in range(GLOBAL_H)]

    # FULL PULL animation: scroll "FULL PULL!!!" once, blink the
    # distance, repeat once more, then stay blank until the sled clears
    # the full_pull flag (next pull). Duration of one scroll = full_w *
    # SCROLL_STEP_MS plus a small tail so the text fully leaves the
    # canvas.
    SCROLL_MS = full_w * SCROLL_STEP_MS
    BLINK_ON_MS = 500
    BLINK_OFF_MS = 300
    BLINK_CYCLES = 3
    BLINK_MS = BLINK_CYCLES * (BLINK_ON_MS + BLINK_OFF_MS)
    # (phase_name, duration_ms). idle has duration 0 -> sticks until mode change.
    FULL_PULL_PHASES = (
        ("scroll", SCROLL_MS),
        ("blink",  BLINK_MS),
        ("scroll", SCROLL_MS),
        ("blink",  BLINK_MS),
        ("idle",   0),
    )

    sw = StopWatch()
    mode = MODE_BLANK
    value = 0
    anchor_ms = 0
    fp_value = 0          # distance to blink during FULL PULL
    fp_phase = 0          # index into FULL_PULL_PHASES
    fp_phase_start = 0    # ms when current phase began

    while True:
        now = sw.time()
        raw = _HUB.ble.observe(SLED_CHANNEL)
        decoded = _decode_sled(raw)
        if decoded is not None:
            new_mode, new_value = decoded
            if new_mode != mode:
                anchor_ms = now
                if new_mode == MODE_FULL_PULL:
                    fp_value = new_value
                    fp_phase = 0
                    fp_phase_start = now
            mode = new_mode
            value = new_value

        if mode == MODE_NUMBER:
            try:
                canvas = render_number(value)
            except KeyError:
                canvas = blank
            _HUB.light.on(Color.WHITE)
        elif mode == MODE_FULL_PULL:
            phase_name, phase_dur = FULL_PULL_PHASES[fp_phase]
            elapsed = now - fp_phase_start
            # Advance to next phase when the current one expires.
            # idle has dur=0 and never advances.
            if phase_dur > 0 and elapsed >= phase_dur and fp_phase < len(FULL_PULL_PHASES) - 1:
                fp_phase += 1
                fp_phase_start = now
                phase_name, phase_dur = FULL_PULL_PHASES[fp_phase]
                elapsed = 0

            if phase_name == "scroll":
                offset = (elapsed // SCROLL_STEP_MS) % full_w
                canvas = render_scroll_frame(full_strip, offset)
                _HUB.light.on(Color.GREEN)
            elif phase_name == "blink":
                slot = elapsed % (BLINK_ON_MS + BLINK_OFF_MS)
                if slot < BLINK_ON_MS:
                    try:
                        canvas = render_number(fp_value)
                    except KeyError:
                        canvas = blank
                else:
                    canvas = blank
                _HUB.light.on(Color.GREEN)
            else:  # idle - blank until sled clears full_pull and a new pull starts
                canvas = blank
                _HUB.light.on(Color.GREEN)
        else:  # MODE_BLANK
            canvas = blank
            _HUB.light.on(Color.RED)

        display.show(local_slice(canvas, hub_index))
        wait(FRAME_MS)
