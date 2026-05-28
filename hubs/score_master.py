# score_master.py
#
# SLED STUB: broadcasts (distance, 0, full_pull_flag) on DISTANCE_CHANNEL,
# i.e. the exact wire format the real sled (hubs/sled.py) uses. Lets you
# verify display_1/2/3 without rigging up the physical sled.
#
# Cycles 0..100 then triggers a full-pull marquee, then repeats.
#
# Deploy with:  python tools/deploy.py scoremaster display1 display2 display3
# (then `python tools/deploy.py sled` once you want the real source.)

from pybricks.hubs import PrimeHub
from pybricks.parameters import Color
from pybricks.tools import wait, StopWatch

DISTANCE_CHANNEL = 2          # must match sled.py DISTANCE_CHANNEL
BROADCAST_MS = 200            # display refresh feels live at this rate
STEP_MS = 250                 # ms per +1 lane metre in the demo
FULL_PULL_HOLD_MS = 6000

_HUB = PrimeHub(broadcast_channel=DISTANCE_CHANNEL)
_HUB.light.on(Color.BLUE)
print("score master start ch=", DISTANCE_CHANNEL,
      "broadcast_ms=", BROADCAST_MS, "step_ms=", STEP_MS)

sw = StopWatch()
cycle_start = sw.time()
CYCLE_MS = 100 * STEP_MS + FULL_PULL_HOLD_MS

while True:
    now = sw.time()
    t = (now - cycle_start) % CYCLE_MS
    if t < 100 * STEP_MS:
        distance = t // STEP_MS         # 0..99
        full_pull = 0
    else:
        distance = 100
        full_pull = 1

    _HUB.ble.broadcast((int(distance), 0, int(full_pull)))
    wait(BROADCAST_MS)
