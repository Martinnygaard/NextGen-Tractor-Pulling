from hubs.display_logic import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    LOCAL_WIDTH,
    LOCAL_HEIGHT,
    FULL_PULL_BASE,
    blank_canvas,
    make_number_canvas,
    make_full_pull_canvas,
    crop_local_canvas,
    rotate_pixels,
    ascii_canvas,
)


def count_on_pixels(canvas):
    return sum(1 for row in canvas for pixel in row if pixel == "1")


def test_blank_canvas_dimensions():
    canvas = blank_canvas()
    assert len(canvas) == DISPLAY_HEIGHT
    assert all(len(row) == DISPLAY_WIDTH for row in canvas)
    assert count_on_pixels(canvas) == 0


def test_make_number_canvas_leading_zeros():
    canvas = make_number_canvas(5)
    assert count_on_pixels(canvas) > 0
    text = ascii_canvas(canvas)
    assert "#" in text


def test_make_number_canvas_three_digits():
    canvas = make_number_canvas(123)
    assert count_on_pixels(canvas) > 0
    assert len(canvas) == DISPLAY_HEIGHT


def test_make_full_pull_canvas_wraps():
    canvas1 = make_full_pull_canvas(0)
    canvas2 = make_full_pull_canvas(FULL_PULL_BASE)
    assert canvas1 != canvas2
    assert len(canvas1) == DISPLAY_HEIGHT
    assert len(canvas1[0]) == DISPLAY_WIDTH


def test_crop_local_canvas_slices():
    global_canvas = blank_canvas()
    for y in range(DISPLAY_HEIGHT):
        for x in range(DISPLAY_WIDTH):
            if x < LOCAL_WIDTH:
                global_canvas[y][x] = "1"
    slice0 = crop_local_canvas(global_canvas, 0)
    slice1 = crop_local_canvas(global_canvas, LOCAL_WIDTH)
    assert count_on_pixels(slice0) == LOCAL_WIDTH * DISPLAY_HEIGHT
    assert count_on_pixels(slice1) == 0


def test_rotate_pixels_90_degrees():
    pixels = [
        "1", "0", "0",
        "0", "1", "0",
        "0", "0", "1",
    ]
    rotated = rotate_pixels(pixels, 90)
    assert rotated[2] == "1"
    assert rotated[4] == "1"
    assert rotated[6] == "1"


def test_ascii_canvas_returns_string():
    canvas = blank_canvas()
    text = ascii_canvas(canvas)
    assert isinstance(text, str)
    assert text.count("\n") == DISPLAY_HEIGHT - 1
