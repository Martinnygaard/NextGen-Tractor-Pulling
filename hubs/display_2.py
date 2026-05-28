# display_2.py - middle display hub. Global columns 6..11.
# See display_1.py.

try:
    from hubs.display_common import boot, run_display, SLED_CHANNEL
except ImportError:
    from display_common import boot, run_display, SLED_CHANNEL

boot(observe_channels=[SLED_CHANNEL])

HUB_INDEX = 1

PORT_GRID = [
    ["B", "A"],
    ["D", "C"],
    ["F", "E"],
]

ROTATION = 270

run_display(HUB_INDEX, PORT_GRID, ROTATION)

