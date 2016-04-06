"""
LNLSGonioBase.py
"""
import logging
from AbstractMotor import AbstractMotor
from HardwareRepository.BaseHardwareObjects import Device
from time import sleep
import gevent

#------------------------------------------------------------------------------
# Constant names from lnls-gonio_base.xml
GONIO_VAL  = 'epicsGonioBase_val'
GONIO_RLV  = 'epicsGonioBase_rlv'
GONIO_RBV  = 'epicsGonioBase_rbv'
GONIO_DMOV = 'epicsGonioBase_dmov'
GONIO_STOP = 'epicsGonioBase_stop'

#------------------------------------------------------------------------------
class LNLSGonioBase(AbstractMotor, Device):      
    (NOTINITIALIZED, UNUSABLE, READY, MOVESTARTED, MOVING, ONLIMIT) = (0,1,2,3,4,5)
    EXPORTER_TO_MOTOR_STATE = { "Invalid": NOTINITIALIZED,
                                "Fault": UNUSABLE,
                                "Ready": READY,
                                "Moving": MOVING,
                                "Created": NOTINITIALIZED,
                                "Initializing": NOTINITIALIZED,
                                "Unknown": UNUSABLE }

    def __init__(self, name):
        AbstractMotor.__init__(self)
        Device.__init__(self, name)

    def init(self): 
        self.motorState = LNLSGonioBase.READY
        # Set current position
        self.motorPosition = self.getPosition()
        self.motorgen = None

    def connectNotify(self, signal):
        if signal == 'positionChanged':
            self.emit('positionChanged', (self.getPosition(), ))
        elif signal == 'stateChanged':
            self.motorStateChanged(self.getState())
        elif signal == 'limitsChanged':
            self.motorLimitsChanged()  
 
    def updateState(self):
        pass

    def updateMotorState(self, motor_state):
        self.motorState = motor_state

    def motorStateChanged(self, state):
        self.emit('stateChanged', (self.motorState, ))

    def getState(self):
        return self.motorState
    
    def motorLimitsChanged(self):
        self.emit('limitsChanged', (self.getLimits(), ))
                     
    def getLimits(self):
        return (-1E4,1E4)
 
    def getPosition(self):
        return self.getValue(GONIO_RBV)

    def getDialPosition(self):
        return self.getPosition()

    def move(self, absolutePosition):
        self.setValue(GONIO_VAL, absolutePosition)
        self.motorState = LNLSGonioBase.MOVING
        self.emit('stateChanged', (self.motorState))
        self.motorgen = gevent.spawn(self.waitEndOfMove, 0.1)

    def moveRelative(self, relativePosition):
        self.setValue(GONIO_RLV, relativePosition)
        self.motorState = LNLSGonioBase.MOVING
        self.emit('stateChanged', (self.motorState))
        self.motorgen = gevent.spawn(self.waitEndOfMove, 0.1)

    def waitEndOfMove(self, timeout=None):
        sleep(0.1)
        while (self.getValue(GONIO_DMOV) == 0):
            self.motorPosition = self.getPosition()
            self.emit('positionChanged', (self.motorPosition))
            sleep(0.1)
        self.motorState = LNLSGonioBase.READY
        self.emit('stateChanged', (self.motorState))
        self.motorPosition = self.getPosition()
        self.emit('positionChanged', (self.motorPosition))
        try:
            self.motorgen.kill()
        except:
            pass

    def syncMoveRelative(self, relative_position, timeout=None):
        self.motorPosition = relative_position

    def syncMove(self, position, timeout=None):
        self.motorPosition = position

    def motorIsMoving(self):
        return (self.getValue(GONIO_DMOV) == 0)

    def getMotorMnemonic(self):
        return self.motor_name

    def stop(self):
        self.setValue(GONIO_STOP, 1)
        sleep(0.2)
        self.setValue(GONIO_STOP, 0)

    def getPredefinedPositionsList(self):
        #For zoom
        return {"Zoom 1": 1, "Zoom 2": 2, "Zoom 3": 3, "Zoom 4": 4, "Zoom 5": 5}
