# BISECT-TEST 6: isolate hub = PrimeHub() instantiation.
print("A")
from pybricks.hubs import PrimeHub
print("B")
hub = PrimeHub()
print("C")
from pybricks.tools import wait
print("D")
wait(200)
print("E")

