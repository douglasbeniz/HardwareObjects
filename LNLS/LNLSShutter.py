from HardwareRepository.BaseHardwareObjects import Device
import logging

SHUTTER = 'safetyShutter'

OPEN  = 1
CLOSE = 0

class LNLSShutter(Device):
    shutterState = {
        0: 'unknown',
        3: 'closed',
        4: 'opened',
        9: 'moving',
        17: 'automatic',
        23: 'fault',
        46: 'disabled',
        -1: 'error'
        }
  
    def __init__(self, name):
        Device.__init__(self, name)

        self.shutterStateValue = 0

    def init(self):
        self.setIsReady(True)

        self.chan_shutter = self.getChannelObject(SHUTTER)
        if self.chan_shutter is not None: 
            self.chan_shutter.connectSignal('update', self.valueChanged)

    def valueChanged(self, value):
        self.shutterStateValue = (4 if (value == OPEN) else 3)
        self.emit('shutterStateChanged', (LNLSShutter.shutterState[self.shutterStateValue], LNLSShutter.shutterState[self.shutterStateValue],))
       
    def getShutterState(self):
        return LNLSShutter.shutterState[self.shutterStateValue] 

    def shutterIsOpen(self):
        return (self.shutterStateValue == OPEN)

    def enableControls(self, enable=True):
        self.emit('enableControls', enable)

    def isShutterOk(self):
        return True

    def openShutter(self):
        # Update shutter
        self.setValue(SHUTTER, OPEN)
        # Update state
        self.shutterStateValue = 4
        self.emit('shutterStateChanged', (LNLSShutter.shutterState[self.shutterStateValue], LNLSShutter.shutterState[self.shutterStateValue],))

    def closeShutter(self):
        # Update shutter
        self.setValue(SHUTTER, CLOSE)
        # Update state
        self.shutterStateValue = 3
        self.emit('shutterStateChanged', (LNLSShutter.shutterState[self.shutterStateValue], LNLSShutter.shutterState[self.shutterStateValue],))
