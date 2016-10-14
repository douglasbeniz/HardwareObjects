"""
LNLSEnergy.py
"""

from HardwareRepository.BaseHardwareObjects import Equipment
import gevent
from time import sleep

#------------------------------------------------------------------------------
# h: Planck constant, h = 6.626 x 10^-34 J s
# c: speed of light, c = 2.9979 10^+8 m/s
# hc: 12.3984 A keV
PLANCK_LIGHT_SPEED = 12.3984

#------------------------------------------------------------------------------
# Constant names from lnls-motor.xml
MOTOR_VAL  = 'epicsMotor_val'
MOTOR_RBV  = 'epicsMotor_rbv'
MOTOR_RLV  = 'epicsMotor_rlv'
MOTOR_DMOV = 'epicsMotor_dmov'
MOTOR_STOP = 'epicsMotor_stop'
MOTOR_DHLM = 'epicsMotor_dhlm'
MOTOR_DLLM = 'epicsMotor_dllm'

# Units
KEV_UNIT = 0
ANG_UNIT = 1

class LNLSEnergy(Equipment):
    (NOTINITIALIZED, UNUSABLE, READY, MOVESTARTED, MOVING, ONLIMIT) = (0,1,2,3,4,5)
    EXPORTER_TO_MOTOR_STATE = { "Invalid": NOTINITIALIZED,
                                "Fault": UNUSABLE,
                                "Ready": READY,
                                "Moving": MOVING,
                                "Created": NOTINITIALIZED,
                                "Initializing": NOTINITIALIZED,
                                "Unknown": UNUSABLE }
    def init(self):
        self.tunable = True
        self.moving = None
        self.motorgen = None
        self.default_en = 12

        self.en_lims = self.get_energy_limits()

        self.energy_value = 12
        self.wavelength_value = PLANCK_LIGHT_SPEED/self.energy_value

        self.motorState = LNLSEnergy.READY

        self.chan_motor_dhlm = self.getChannelObject(MOTOR_DHLM)
        self.chan_motor_dllm = self.getChannelObject(MOTOR_DLLM)

        self.chan_motor_rbv = self.getChannelObject(MOTOR_RBV)
        if self.chan_motor_rbv is not None: 
            self.chan_motor_rbv.connectSignal('update', self.positionChanged)

        self.chan_motor_dmov = self.getChannelObject(MOTOR_DMOV)
        if self.chan_motor_dmov is not None: 
            self.chan_motor_dmov.connectSignal('update', self.statusChanged)

        self.canMoveEnergy = self.can_move_energy
        self.move_energy = self.start_move_energy 
        self.getEnergyLimits  = self.get_energy_limits
        self.getWavelengthLimits = self.get_wavelength_limits
        self.setEnergy = self.set_energy
        self.setWavelength = self.set_wavelength
        self.getCurrentEnergy = self.get_current_energy
        self.getCurrentWavelength = self.get_current_wavelength

    def update_values(self):
        self.emit("energyChanged", (self.energy_value, self.wavelength_value))
        self.emit('stateChanged', (self.motorState))

    def can_move_energy(self):
        return self.tunable

    def isConnected(self):
        return True

    def get_current_energy(self):
        self.energy_value = round(self.getValue(MOTOR_RBV) / 1000, 4)
        return self.energy_value

    def get_current_wavelength(self):
        current_en = self.get_current_energy()
        if current_en is not None:
            return (PLANCK_LIGHT_SPEED/current_en)
        return None

    def get_energy_limits(self):
        return (round(self.getValue(MOTOR_DLLM) / 1000, 4), round(self.getValue(MOTOR_DHLM) / 1000, 4))

    def get_wavelength_limits(self):
        lims = None
        self.en_lims = self.getEnergyLimits()
        if self.en_lims is not None:
            lims=(PLANCK_LIGHT_SPEED/self.en_lims[1], PLANCK_LIGHT_SPEED/self.en_lims[0])
        return lims

    def start_move_energy(self, value, unit, wait=False):
        if (unit == KEV_UNIT):
            self.energy_value = value
        elif (unit == ANG_UNIT):
            self.energy_value = PLANCK_LIGHT_SPEED / value

        self.setValue(MOTOR_VAL, self.energy_value * 1000)

    def set_energy(self, value):
        self.start_move_energy(value, KEV_UNIT, wait=True)

    def set_wavelength(self, value):
        self.start_move_energy(value, ANG_UNIT, wait=True)

    def positionChanged(self, value):
        if value is not None:
            self.energy_value = round(value / 1000, 4)
            self.wavelength_value =  round(PLANCK_LIGHT_SPEED/self.energy_value, 3)
            
            self.update_values()

    def statusChanged(self, value):
        if (value == 0):
            self.motorState = LNLSEnergy.MOVING
        elif (value == 1):
            self.motorState = LNLSEnergy.READY

        self.update_values()

    def getState(self):
        return self.motorState

    def stop(self):
        self.setValue(MOTOR_STOP, 1)
        sleep(0.2)
        self.setValue(MOTOR_STOP, 0)
