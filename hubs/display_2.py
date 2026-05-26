# BISECT-13: visuel LED-test (ingen stdout dependence)
from pybricks.hubs import PrimeHub
from pybricks.tools import wait
hub = PrimeHub()
hub.light.on("blue")
wait(2000)
hub.light.on("yellow")
wait(2000)
hub.light.off()