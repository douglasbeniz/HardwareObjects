"""
LNLSResolution.py
"""

from HardwareRepository import BaseHardwareObjects
import gevent
import logging
import math
from time import sleep

#------------------------------------------------------------------------------
# h: Planck constant, h = 6.626 x 10^-34 J s
# c: speed of light, c = 2.9979 10^+8 m/s
# hc: 12.3984 A keV
PLANCK_LIGHT_SPEED = 12.3984

class LNLSResolution(BaseHardwareObjects.Equipment):
    def _init(self):
        self.connect("equipmentReady", self.equipmentReady)
        self.connect("equipmentNotReady", self.equipmentNotReady)

        return BaseHardwareObjects.Equipment._init(self)

    def init(self):
        # Related hardware objects
        self.detector_hwobj = self.getObjectByRole("detector")
        self.energy_hwobj = self.getObjectByRole("energy")        

        self.resolution = self.defaultResolution
        self.wavelength = self.defaultWavelength
        self.energy = self.defaultEnergy

        # Connect signals to related objects
        if (self.detector_hwobj):
            self.detector_hwobj.connect('positionChanged', self.detectorDistanceChanged)
            self.detector_hwobj.connect('stateChanged', self.detectorDistanceStateChanged)

        if (self.energy_hwobj):
            self.energy_hwobj.connect('energyChanged', self.energyChanged)

    def beam_centre_updated(self, beam_pos_dict):
        pass

    def getWavelength(self):
        if self.wavelength is None:
            if self.energy is None:
                if (self.energy_hwobj):
                    return self.energy_hwobj.getCurrentWavelength()
                else:
                    return None
            else:
                # Update wavelenght
                self.wavelength = (PLANCK_LIGHT_SPEED / self.energy)
                # Return it
                return self.wavelength
        else:
            return self.wavelength

    def wavelengthChanged(self, wavelength=None):
        if wavelength is None:
            wavelength = self.getWavelength()
        # Store new value of wavelength
        self.wavelength = wavelength

        # Force the update of resolution
        self.recalculateResolution()

        # Update status
        self.update_values(energyReference = True)

    def energyChanged(self, energy, wavelength=None):
        if (energy != self.energy):
            # energy in KeV
            self.energy = energy

        if (wavelength is None):
            # Update wavelength
            self.wavelengthChanged(PLANCK_LIGHT_SPEED / energy)
        else:
            self.wavelengthChanged(wavelength)

    def set_energy(self, energy):
        # energy in KeV
        self.energy = energy
        # Update wavelength
        self.energyChanged(energy)

    def recalculateResolution(self):
        # Update resolution calculanting it from current distance
        self.set_resolution(self.dist2res())

    def detectorDistanceChanged(self, value):
        # Update resolution calculanting it from current distance
        self.set_resolution(self.dist2res(value))
        # Emit update to UI
        self.emit('positionChanged', (self.resolution,))

    def detectorDistanceStateChanged(self, value):
        # Emit update to UI
        self.emit('stateChanged', (value,))

    def update_values(self, energyReference=False):
        # Call the update of Detector
        if (self.detector_hwobj):
            self.detector_hwobj.update_values()

        # Send information of Resolution
        self.emit("positionChanged", (self.resolution,))
        if (energyReference):
            self.emit('stateChanged', (self.getEnergyState()))
        else:
            self.emit('stateChanged', (self.getDetectorState()))

    def res2dist(self, res=None):
        # ----------------------------------------------------------------------
        #  Dist = Radius/(math.tan(2*math.asin(WL/(2*Res))))
        # ----------------------------------------------------------------------
        # Dist    : Detector distance
        # Radius  : Pilatus half of height (radius)
        # WL      : Wavelength of selected energy
        # Res     : Resolution

        if res is None:
            res = self.getPosition()

        try:
            ttheta = (2 * math.asin(self.getWavelength() / (2 * res)))
            return (self.detector_hwobj.get_radius() / math.tan(ttheta))
        except:
            logging.getLogger().exception("error while calculating resolution to distance")
            return None

    def dist2res(self, dist=None):
        # ----------------------------------------------------------------------
        #  Res = WL / (2*math.sin(math.atan(Radius/Dist)/2))
        # ----------------------------------------------------------------------
        # Dist    : Detector distance
        # Radius  : Pilatus half of height (radius)
        # WL      : Wavelength of selected energy
        # Res     : Resolution

        if dist is None:
            dist = self.getDetectorDistance()

        try:
            ttheta = math.atan(self.detector_hwobj.get_radius() / dist)
            return self.getWavelength() / (2 * math.sin(ttheta / 2))
        except:
            logging.getLogger().exception("error while calculating distance to resolution")
            return None

    def equipmentReady(self):
        self.emit("deviceReady")

    def equipmentNotReady(self):
        self.emit("deviceNotReady")

    def getPosition(self):
        return self.resolution

    def get_value(self):
        return self.getPosition()

    def set_resolution(self, res):
        self.newResolution(res)

    def newResolution(self, res):
        self.resolution = res
        self.emit("positionChanged", (res, ))

    def getState(self):
        return self.getDetectorState()

    def connectNotify(self, signal):
        pass

    def getLimits(self, callback=None, error_callback=None):
        return (0, 20)

    def getDetectorDistance(self):
        if (self.detector_hwobj):
            return self.detector_hwobj.get_distance()
        else:
            return None

    def getDetectorState(self):
        if (self.detector_hwobj):
            return self.detector_hwobj.distance_motor_hwobj.getState()
        else:
            return None

    def getEnergyState(self):
        if (self.energy_hwobj):
            return self.energy_hwobj.getState()
        else:
            return None

    def detectorIsMoving(self):
        if (self.detector_hwobj):
            return self.detector_hwobj.distance_motor_hwobj.isMoving()
        else:
            return None

    def move(self, res=None, wait=False):
        if res is None:
            res = self.getPosition()

        #logging.getLogger().info("move Resolution to %s", res)

        # Move detector distance motor
        if self.detector_hwobj is not None:
            # Calculate distance based on resolution
            distance = self.res2dist(res)
            # Start a monitoring
            self.detectorgen = gevent.spawn(self.waitEndOfMove, 0.1)
            # Move detector distance to specific position
            self.detector_hwobj.move_detector_distance(distance, wait=wait)
        else:
            logging.getLogger().exception("no detector configure in resolution object!")

    def waitEndOfMove(self, timeout=None):
        sleep(0.1)
        if (self.detectorIsMoving()):
            self.emit('stateChanged', (self.getDetectorState()))

        while (self.detectorIsMoving()):
            # Update resolution calculanting it from current distance
            self.set_resolution(self.dist2res(self.getDetectorDistance()))
            # Emit updates to UI
            self.update_values()
            sleep(0.1)

        # Wait a while more for total motor end of movement....
        maxTries = 60
        tryNumber = 0

        while ((tryNumber < maxTries) and (self.getDetectorState() == self.detector_hwobj.distance_motor_hwobj.MOVING)):
            sleep(0.1)
            tryNumber += 1

        # Update resolution calculanting it from current distance
        self.set_resolution(self.dist2res(self.getDetectorDistance()))

        # Emit updates to UI
        self.emit('stateChanged', (self.getDetectorState()))
        self.update_values()

    def motorIsMoving(self):
        return False

    def newDistance(self, dist):
        pass

    def stop(self):
        self.detector_hwobj.distance_motor_hwobj.stop()
