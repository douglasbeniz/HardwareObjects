"""
LNLSLight.py
"""

from HardwareRepository.BaseHardwareObjects import Equipment
import gevent
from time import sleep

# -----------------------------------------------------------------------------
LIGHT = 'epicsLight'

# -----------------------------------------------------------------------------
class LNLSLight(Equipment):
    def init(self):
        self.moving = None
        self.intensityValue = None

        self.chan_light = self.getChannelObject(LIGHT)
        if self.chan_light is not None: 
            self.chan_light.connectSignal('update', self.intensityChanged)

    def update_values(self):
        self.emit("intensityChanged", (self.intensityValue))

    def isConnected(self):
        return True

    def get_current_intensity(self):
        self.intensityValue = self.getValue(LIGHT)
        return self.intensityValue    

    def set_intensity(self, value):
        self.setValue(LIGHT, value, wait=False)

    def intensityChanged(self, value):
        if value is not None:
            self.intensityValue = value
            self.update_values()
