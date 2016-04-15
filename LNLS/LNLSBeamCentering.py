"""
LNLSBeamFocus.py
"""
import logging
from HardwareRepository.BaseHardwareObjects import Equipment
from time import sleep
import gevent

#------------------------------------------------------------------------------
# Constant names from lnls-beam-focus.xml
# BASE SLIT X1
BASE_SLIT_X1_VAL = 'epicsSlitBaseX1_val'
BASE_SLIT_X1_RLV = 'epicsSlitBaseX1_rlv'
BASE_SLIT_X1_RBV = 'epicsSlitBaseX1_rbv'
BASE_SLIT_X1_DMOV = 'epicsSlitBaseX1_dmov'
BASE_SLIT_X1_STOP = 'epicsSlitBaseX1_stop'
BASE_SLIT_X1_HLS = 'epicsSlitBaseX1_hls'
BASE_SLIT_X1_LLS = 'epicsSlitBaseX1_lls'
# BASE SLIT Z1
BASE_SLIT_Z1_VAL = 'epicsSlitBaseZ1_val'
BASE_SLIT_Z1_RLV = 'epicsSlitBaseZ1_rlv'
BASE_SLIT_Z1_RBV = 'epicsSlitBaseZ1_rbv'
BASE_SLIT_Z1_DMOV = 'epicsSlitBaseZ1_dmov'
BASE_SLIT_Z1_STOP = 'epicsSlitBaseZ1_stop'
BASE_SLIT_Z1_HLS = 'epicsSlitBaseZ1_hls'
BASE_SLIT_Z1_LLS = 'epicsSlitBaseZ1_lls'
# KEITHLEY 6517A
K6517A_VAL = 'epicsKeithley6517A_measure'

#------------------------------------------------------------------------------
class LNLSBeamCentering(Equipment):
    """
    Descript. :
    """
    def __init__(self, name):
        """
        Descript. :
        """
        Equipment.__init__(self, name) 

        # Attributes which should be set by GUI
        self._distanceHor = None
        self._distanceVer = None


    def init(self):
        """
        Descript. :
        """
        self.beamcenter_gen = None

    def setDistanceHorizontal(self, distance_hor):
        self._distanceHor = float(distance_hor)

    def setDistanceVertical(self, distance_ver):
        self._distanceVer = float(distance_ver)

    def _centerProcedure(self, timeout=None):
        # Procedure to find position where intensity of beam is highest
        max_intensity_horizontal = 0
        pos_max_intensity_hor = 0
        initialBaseSlitX1 = self.getValue(BASE_SLIT_X1_RBV)

        self.emit('plotClearHorizontal')
        # Move until physical limit which block movement at one side
        physicalLimit = False
        while(not physicalLimit):
            currentRBV = self.getValue(BASE_SLIT_X1_RBV)
            self.setValue(BASE_SLIT_X1_RLV, -0.05)
            sleep(0.2)
            newRBV = self.getValue(BASE_SLIT_X1_RBV)
            if ((newRBV <= (initialBaseSlitX1 - self._distanceHor)) or (newRBV == currentRBV)):
                physicalLimit = True
                continue
            self.emit('positionHorChanged', (newRBV, ))
            intensity = self.getValue(K6517A_VAL)
            self.emit('intensityChanged', (intensity, ))

            self.emit('plotNewPointHorizontal', (newRBV, intensity,))
            if (intensity > max_intensity_horizontal):
                pos_max_intensity_hor = self.getValue(BASE_SLIT_X1_RBV)

        self.emit('plotClearHorizontal')
        # Move until physical limit which block movement at other side
        physicalLimit = False
        while(not physicalLimit):
            currentRBV = self.getValue(BASE_SLIT_X1_RBV)
            self.setValue(BASE_SLIT_X1_RLV, 0.05)
            sleep(0.2)
            newRBV = self.getValue(BASE_SLIT_X1_RBV)
            if ((newRBV >= (initialBaseSlitX1 + self._distanceHor)) or (newRBV == currentRBV)):
                physicalLimit = True
                continue
            self.emit('positionHorChanged', (newRBV, ))
            intensity = self.getValue(K6517A_VAL)
            self.emit('intensityChanged', (intensity, ))

            self.emit('plotNewPointHorizontal', (newRBV, intensity,))
            if (intensity > max_intensity_horizontal):
                pos_max_intensity_hor = self.getValue(BASE_SLIT_X1_RBV)

        # Move to the position of maximum intensity
        self.setValue(BASE_SLIT_X1_VAL, pos_max_intensity_hor)

        # Doing the same at vertical...

        max_intensity_vertical = 0
        pos_max_intensity_ver = 0
        initialBaseSlitZ1 = self.getValue(BASE_SLIT_Z1_RBV)

        self.emit('plotClearVertical')
        # Move until physical limit which block movement at one side
        physicalLimit = False
        while(not physicalLimit):
            currentRBV = self.getValue(BASE_SLIT_Z1_RBV)
            self.setValue(BASE_SLIT_Z1_RLV, -0.05)
            sleep(0.2)
            newRBV = self.getValue(BASE_SLIT_Z1_RBV)
            if ((newRBV <= (initialBaseSlitZ1 - self._distanceVer)) or (newRBV == currentRBV)):
                physicalLimit = True
                continue
            self.emit('positionVerChanged', (newRBV, ))
            intensity = self.getValue(K6517A_VAL)
            self.emit('intensityChanged', (intensity, ))

            self.emit('plotNewPointVertical', (newRBV, intensity,))
            if (intensity > max_intensity_vertical):
                pos_max_intensity_ver = self.getValue(BASE_SLIT_Z1_RBV)

        self.emit('plotClearVertical')
        # Move until physical limit which block movement at other side
        physicalLimit = False
        while(not physicalLimit):
            currentRBV = self.getValue(BASE_SLIT_Z1_RBV)
            self.setValue(BASE_SLIT_Z1_RLV, 0.05)
            sleep(0.2)
            newRBV = self.getValue(BASE_SLIT_Z1_RBV)
            if ((newRBV >= (initialBaseSlitZ1 + self._distanceVer)) or (newRBV == currentRBV)):
                physicalLimit = True
                continue
            self.emit('positionVerChanged', (newRBV, ))
            intensity = self.getValue(K6517A_VAL)
            self.emit('intensityChanged', (intensity, ))

            self.emit('plotNewPointVertical', (newRBV, intensity,))
            if (intensity > max_intensity_vertical):
                pos_max_intensity_ver = self.getValue(BASE_SLIT_Z1_RBV)

        # Move to the position of maximum intensity
        self.setValue(BASE_SLIT_Z1_VAL, pos_max_intensity_ver)

        self.emit('centeringConcluded')

    def start(self):
        """
        Descript. : 
        """
        # Start a new thread to run centering...
        self.beamcenter_gen = gevent.spawn(self._centerProcedure, 0.1)

    def cancel(self):
        """
        Descript. : 
        """
        print("Called cancel centering....")
        if (self.beamcenter_gen):
            try:
                self.beamcenter_gen.kill()
            except:
                print("ERROR! Trying to kill gevent of beam-centering....")
                pass
