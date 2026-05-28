# display_3.py - rightmost display hub. Global columns 12..17.
# See display_1.py.

try:
    from hubs.display_common import boot, run_display, SLED_CHANNEL
except ImportError:
    from display_common import boot, run_display, SLED_CHANNEL

boot(observe_channels=[SLED_CHANNEL])

HUB_INDEX = 2

PORT_GRID = [
    ["B", "A"],
    ["D", "C"],
    ["F", "E"],
]

ROTATION = 270

run_display(HUB_INDEX, PORT_GRID, ROTATION)

