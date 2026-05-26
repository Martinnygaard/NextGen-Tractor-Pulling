# BISECT-14: visuel LED-test med korrekt Color-API
from pybricks.hubs import PrimeHub
from pybricks.parameters import Color
from pybricks.tools import wait
hub = PrimeHub()
hub.light.on(Color.BLUE)
wait(2000)
hub.light.on(Color.YELLOW)
wait(2000)
hub.light.off()
print("BISECT14_DONE")