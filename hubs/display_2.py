# BISECT-TEST: progressively exercise imports + hub init.
print("A: top")

from pybricks.hubs import PrimeHub
print("B: imported PrimeHub")

from pybricks.parameters import Color, Port
print("C: imported Color, Port")

from pybricks.tools import wait
print("D: imported wait")

from pybricks.pupdevices import ColorLightMatrix
print("E: imported ColorLightMatrix")

hub = PrimeHub()
print("F: hub instantiated")

print("G: starting wait loop")
for i in range(10):
    print("tick", i)
    wait(500)
print("Z: done")

