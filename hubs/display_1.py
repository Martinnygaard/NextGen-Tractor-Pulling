# display_1.py - leftmost display hub. Global columns 0..5.
#
# Observes SLED_CHANNEL directly: the sled (hubs/sled.py) broadcasts
# (distance_int, ack_seq, full_pull_flag) and the display decodes that
# into either MODE_NUMBER (show distance) or MODE_FULL_PULL (scroll
# "FULL PULL!!!"). No master hub is involved.
#
# Same wrapper for all three displays modulo HUB_INDEX.

try:
    from hubs.display_common import boot, run_display, SLED_CHANNEL
except ImportError:
    from display_common import boot, run_display, SLED_CHANNEL

boot(observe_channels=[SLED_CHANNEL])

HUB_INDEX = 0

PORT_GRID = [
    ["B", "A"],
    ["D", "C"],
    ["F", "E"],
]

ROTATION = 270  # per-panel rotation in degrees (0/90/180/270)

run_display(HUB_INDEX, PORT_GRID, ROTATION)

