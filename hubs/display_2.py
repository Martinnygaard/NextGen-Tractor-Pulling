# BISECT-TEST 8: re-run bisect-4 to check determinism.
print("A")
from pybricks.hubs import PrimeHub
print("B")
from pybricks.parameters import Color, Port
print("C")
from pybricks.tools import wait
print("D")
from pybricks.pupdevices import ColorLightMatrix
print("E")
hub = PrimeHub()
print("F")
for i in range(10):
    print("tick", i)
    wait(500)
print("Z")

