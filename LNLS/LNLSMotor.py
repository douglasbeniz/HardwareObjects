"""
LNLSMotor.py
"""
import logging
from AbstractMotor import AbstractMotor
from HardwareRepository.BaseHardwareObjects import Device
from time import sleep
import gevent

#------------------------------------------------------------------------------
# Constant names from lnls-gonio_base.xml
SLIT_VAL  = 'epicsMotor_val'
SLIT_RLV  = 'epicsMotor_rlv'
SLIT_RBV  = 'epicsMotor_rbv'
SLIT_DMOV = 'epicsMotor_dmov'
SLIT_STOP = 'epicsMotor_stop'

#------------------------------------------------------------------------------
class LNLSMotor(AbstractMotor, Device):      
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
        self.motorState = LNLSMotor.READY
        # Set current position
        self.motorPosition = self.getPosition()
        self.motorgen = None

        self.monitorgen = None

    def monitor(self, monitor):
        if (monitor):
            self.monitorgen = gevent.spawn(self.monitorMovement)
        else:
            try:
                self.monitorgen.kill()
            except:
                print("ERROR! Trying to kill gevent of motor-monitoring....")
                pass

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
        return self.getValue(SLIT_RBV)

    def getDialPosition(self):
        return self.getPosition()

    def move(self, absolutePosition):
        self.setValue(SLIT_VAL, absolutePosition)
        self.motorgen = gevent.spawn(self.waitEndOfMove, 0.1)

    def moveRelative(self, relativePosition):
        self.setValue(SLIT_RLV, relativePosition)
        self.motorgen = gevent.spawn(self.waitEndOfMove, 0.1)

    def monitorMovement(self):
        while True:
            if (self.getValue(SLIT_DMOV) == 0):
                self.waitEndOfMove(5)
            sleep(0.1)

    def waitEndOfMove(self, timeout=None):
        sleep(0.1)
        if (self.getValue(SLIT_DMOV) == 0):
            self.motorState = LNLSMotor.MOVING
            self.emit('stateChanged', (self.motorState))

        while (self.getValue(SLIT_DMOV) == 0):
            self.motorPosition = self.getPosition()
            self.emit('positionChanged', (self.motorPosition))
            sleep(0.1)
        self.motorState = LNLSMotor.READY
        self.emit('stateChanged', (self.motorState))
        self.motorPosition = self.getPosition()
        self.emit('positionChanged', (self.motorPosition))

    def syncMoveRelative(self, relative_position, timeout=None):
        self.motorPosition = relative_position

    def syncMove(self, position, timeout=None):
        self.motorPosition = position

    def motorIsMoving(self):
        return (self.getValue(SLIT_DMOV) == 0)

    def getMotorMnemonic(self):
        return self.motor_name

    def stop(self):
        self.setValue(SLIT_STOP, 1)
        sleep(0.2)
        self.setValue(SLIT_STOP, 0)
