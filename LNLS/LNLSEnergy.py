"""
LNLSEnergy.py
"""

import gevent
import math
import logging

from time import sleep
from datetime import datetime

from HardwareRepository.BaseHardwareObjects import Equipment

#------------------------------------------------------------------------------
# h: Planck constant, h = 6.626 x 10^-34 J s
# c: speed of light, c = 2.9979 10^+8 m/s
# hc: 12.39858 A keV
PLANCK_LIGHT_SPEED = 12.39858
PLANCK_LIGHT_SPEED_EV = (PLANCK_LIGHT_SPEED * 1000)

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
        # ----------------------------------------------------------------------
        # Initialize some parameters
        self.tunable = True
        self.moving = None
        self.motorgen = None
        self.energy_value = None
        self.wavelength_value = None
        self.default_en = 12
        self.setting_threshold = False
        self.wait_threshold = 60        # time to wait for camServer to set Pilatus Threshold
        self.motorState = LNLSEnergy.READY

        # ----------------------------------------------------------------------
        # Hardware objects
        self.mono_first_xtal_hwobj = self.getObjectByRole("mono_first_xtal")
        self.mono_second_xtal_hwobj = self.getObjectByRole("mono_second_xtal")
        self.detector_hwobj = self.getObjectByRole("detector")

        # Connect signals to related objects
        if (self.mono_first_xtal_hwobj):
            self.mono_first_xtal_hwobj.connect('positionChanged', self.positionChanged)
            self.mono_first_xtal_hwobj.connect('stateChanged', self.statusChanged)

        if (self.mono_second_xtal_hwobj):
            self.mono_second_xtal_hwobj.connect('positionChanged', self.positionChanged)
            self.mono_second_xtal_hwobj.connect('stateChanged', self.statusChanged)

        # Initialization that depends on other objects
        self.en_lims = self.get_energy_limits()

        # Alias to some methods
        self.canMoveEnergy = self.can_move_energy
        self.move_energy = self.start_move_energy 
        self.getEnergyLimits  = self.get_energy_limits
        self.getWavelengthLimits = self.get_wavelength_limits
        self.setEnergy = self.set_energy
        self.setWavelength = self.set_wavelength
        self.getPosition = self.get_current_energy
        self.getCurrentEnergy = self.get_current_energy
        self.getCurrentWavelength = self.get_current_wavelength

    def update_values(self):
        self.emit("energyChanged", (self.energy_value, self.wavelength_value))
        self.emit('stateChanged', (self.motorState))

    def can_move_energy(self):
        return self.tunable

    def isConnected(self):
        return True

    def theta2energy(self, angleInDegrees):
        # Formula to convert theta2energy (1st Crystal):
        #     cr_param: crystal param, distance between atomic layers in a Si-111 crystal (2d in angstroms)
        #     theta: angle of mono theta of first crystal in degrees
        #     lambda: cr_param * sin(theta*PI/180.0);
        #     ---
        #     theta2energy = (12398.58/lambda);

        # -------------------------------------------------------------------
        # Calculates current energy based on the position of first mono theta crystal
        currentPosition = angleInDegrees * math.pi / 180.0

        # Calculates lambda
        currentLambda = self.crystal_param_si_111 * math.sin(currentPosition);
        if (abs(currentLambda) > 1E-6):
            try:
                energy = PLANCK_LIGHT_SPEED_EV / currentLambda;
            except:
                energy = 0
        else:
            energy = 1E6

        return energy


    def get_current_energy(self):
        if (hasattr(self, 'crystal_param_si_111') and hasattr(self, 'crystal_offset')):
            # Convert theta2energy (1st Crystal):
            if (self.mono_first_xtal_hwobj):
                energy = self.theta2energy(self.mono_first_xtal_hwobj.getPosition())

            # Set the current energy in KeV
            self.energy_value = (energy / 1000)
        else:
            logging.getLogger("HWR").error('Missing parameters that define the crystal in lnls-energy.xml...')

        return self.energy_value


    def get_current_wavelength(self):
        current_en = self.get_current_energy()
        if current_en is not None:
            self.wavelength_value = (PLANCK_LIGHT_SPEED/current_en)
            return self.wavelength_value
        return None


    def get_energy_limits(self):
        min_energy = None
        max_energy = None

        if (self.mono_first_xtal_hwobj):
            motorLimits = self.mono_first_xtal_hwobj.getLimits()

            min_energy = round(self.theta2energy(motorLimits[1]) / 1000, 4)
            max_energy = round(self.theta2energy(motorLimits[0]) / 1000, 4)

        return (min_energy, max_energy)


    def get_wavelength_limits(self):
        lims = None
        self.en_lims = self.getEnergyLimits()
        if self.en_lims is not None:
            lims=(PLANCK_LIGHT_SPEED/self.en_lims[1], PLANCK_LIGHT_SPEED/self.en_lims[0])
        return lims


    def start_move_energy(self, value, unit, wait=False):
        # Check if needed parameters are set
        if (hasattr(self, 'crystal_param_si_111') and hasattr(self, 'crystal_offset')):
            # Check the necessity to convert energy from resolution
            if (unit == KEV_UNIT):
                self.energy_value = value
            elif (unit == ANG_UNIT):
                self.energy_value = PLANCK_LIGHT_SPEED / value

            # 
            startToChangeThreshold = datetime.now()

            # Set threshold of Pilatus, if necessary
            if (self.detector_hwobj):
                # Verify if we are still setting a previous energy...
                if (self.isSettingThreshold()):
                    logging.getLogger("user_level_log").error('Still changing Pilatus threshold... please, wait a while...')

                    tries = 0
                    while (self.isSettingThreshold() and tries < self.wait_threshold):
                        sleep(1)
                        tries += 1

                # Energy in eV
                self.setting_threshold = True

                changedThreshold = self.detector_hwobj.set_threshold(self.energy_value/2, wait=wait)
                if (changedThreshold):
                    logging.getLogger("user_level_log").error('Changing Pilatus threshold to %.3f, please, wait a while...' % (self.energy_value/2))
                else:
                    self.setting_threshold = False

            # Formula to convert energy2theta (1st Crystal):
            #     E: energy in eV
            #     cr_param: crystal param, distance between atomic layers in a Si-111 crystal (2d in angstroms)
            #     ---
            #     lambda: 12398.58/E;
            #     energy2theta = (asin(lambda/cr_param)*180.0/PI);

            # -------------------------------------------------------------------
            # Calculates target motor positions based on the given energy (in KeV)
            try:
                # First of all, calculate the target angle in radian
                targetAngleInRadian = math.asin(PLANCK_LIGHT_SPEED_EV / self.crystal_param_si_111 / (self.energy_value * 1000))

                # Target for motor of first mono theta crystal
                targetPositionFirstXtal = targetAngleInRadian * 180.0 / math.pi
                if (self.mono_first_xtal_hwobj):
                    self.mono_first_xtal_hwobj.move(targetPositionFirstXtal, wait=wait)

                # Target for motor of second mono theta crystal
                targetPositionSecondXtal = 0.5 * self.crystal_offset / math.cos(targetAngleInRadian)

                if (self.mono_second_xtal_hwobj):
                    self.mono_second_xtal_hwobj.move(targetPositionSecondXtal, wait=wait)
                # 
                endToChangeThreshold = datetime.now()
                # 
                deltaTimeThreshold = endToChangeThreshold - startToChangeThreshold
                deltaTimeThreshold = deltaTimeThreshold.total_seconds()
                # 
                remainingTimeToWait = (self.wait_threshold - deltaTimeThreshold) if changedThreshold else 0
                # 
                if (remainingTimeToWait > 0):
                    if (wait):
                        self.wait_setting_threshold(remainingTimeToWait)
                    else:
                        gevent.spawn(self.wait_setting_threshold, remainingTimeToWait)

            except (ValueError, ZeroDivisionError):
                logging.getLogger("user_level_log").error('Error calculating target angle...')
        else:
            logging.getLogger("HWR").error('Missing parameters that define the crystal in lnls-energy.xml...')


    def wait_setting_threshold(self, timeToWait):
        sleep(timeToWait)
        self.setting_threshold = False
        # Informing user we finished
        logging.getLogger("user_level_log").error('New Pilatus threshold set to %.3f!' % (self.energy_value/2))


    def isSettingThreshold(self):
        return (self.setting_threshold)


    def set_energy(self, value):
        #self.start_move_energy(value, KEV_UNIT, wait=True)
        self.start_move_energy(value, KEV_UNIT, wait=False)


    def set_wavelength(self, value):
        #self.start_move_energy(value, ANG_UNIT, wait=True)
        self.start_move_energy(value, ANG_UNIT, wait=False)


    def getEgu(self):
        return "KeV"


    def positionChanged(self, value):
        if value is not None:
            # Get information from real motors
            self.get_current_energy()
            self.get_current_wavelength()
            # Update information in the UI
            self.update_values()


    def statusChanged(self, value):
        if (self.mono_first_xtal_hwobj and self.mono_second_xtal_hwobj):
            if (self.mono_first_xtal_hwobj.isMoving() or self.mono_second_xtal_hwobj.isMoving()):
                self.motorState = LNLSEnergy.MOVING
            else:
                self.motorState = LNLSEnergy.READY
        else:
            self.motorState = LNLSEnergy.UNUSABLE

        self.update_values()


    def getState(self):
        return self.motorState


    def energyIsReady(self):
        return (self.getState() == LNLSEnergy.READY)


    def stop(self):
        if (self.mono_first_xtal_hwobj and self.mono_second_xtal_hwobj):
            self.mono_first_xtal_hwobj.stop()
            self.mono_second_xtal_hwobj.stop()
