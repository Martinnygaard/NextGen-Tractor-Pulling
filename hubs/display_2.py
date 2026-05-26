# BISECT-TEST 9: all imports + hub + Z (no loop).
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
print("Z")

