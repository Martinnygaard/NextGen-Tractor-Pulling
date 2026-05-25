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
