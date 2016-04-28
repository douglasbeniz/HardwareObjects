"""
LNLSBeamFocus.py
"""
import logging
from HardwareRepository.BaseHardwareObjects import Equipment
from time import sleep
import gevent

#------------------------------------------------------------------------------
# Constant names from lnls-beam-focus.xml
# [0][0][0]: Slit1 - X1 - VAL
# [0][0][1]: Slit1 - X1 - RLV
# [0][0][2]: Slit1 - X1 - RBV
# [0][0][3]: Slit1 - X1 - DMOV
# [0][0][4]: Slit1 - X1 - STOP
# [0][0][5]: Slit1 - X1 - HLS
# [0][0][6]: Slit1 - X1 - LLS
# [0][0][7]: Slit1 - X1 - HLM
# [0][0][8]: Slit1 - X1 - LLM
# [0][1]   : Slit1 - Z1
# [1]      : Slit2

BASE_SLIT = [[['slit1BaseX1_val', 'slit1BaseX1_rlv', 'slit1BaseX1_rbv', 'slit1BaseX1_dmov', 'slit1BaseX1_stop', 'slit1BaseX1_hls', 'slit1BaseX1_lls', 'slit1BaseX1_hlm', 'slit1BaseX1_llm'],
              ['slit1BaseZ1_val', 'slit1BaseZ1_rlv', 'slit1BaseZ1_rbv', 'slit1BaseZ1_dmov', 'slit1BaseZ1_stop', 'slit1BaseZ1_hls', 'slit1BaseZ1_lls', 'slit1BaseZ1_hlm', 'slit1BaseZ1_llm']],
             [['slit2BaseX1_val', 'slit2BaseX1_rlv', 'slit2BaseX1_rbv', 'slit2BaseX1_dmov', 'slit2BaseX1_stop', 'slit2BaseX1_hls', 'slit1BaseX2_lls', 'slit2BaseX1_hlm', 'slit1BaseX2_llm'],
              ['slit2BaseZ1_val', 'slit2BaseZ1_rlv', 'slit2BaseZ1_rbv', 'slit2BaseZ1_dmov', 'slit2BaseZ1_stop', 'slit2BaseZ1_hls', 'slit1BaseZ2_lls', 'slit2BaseZ1_hlm', 'slit1BaseZ2_llm']]]
# KEITHLEY 6517A for while
COUNTER_VAL = ['counter1_val', 'counter2_val']

# Horizontal = X
# Vertical   = Z
POS_CHANGED_SIGN = [['positionHorSlit1Changed','positionVerSlit1Changed'], ['positionHorSlit2Changed','positionVerSlit2Changed']]
CLEAR_SIGN = [['plotClearHorSlit1','plotClearVerSlit1'], ['plotClearHorSlit2','plotClearVerSlit2']]
PLOT_SIGN = [['plotNewPointHorSlit1','plotNewPointVerSlit1'], ['plotNewPointHorSlit2','plotNewPointVerSlit2']]
INT_CHANGED_SIGN = ['intensitySlit1Changed','intensitySlit2Changed']
SET_TAB_SIGN = [['setTabHorSlit1','setTabVerSlit1'], ['setTabHorSlit2','setTabVerSlit2']]

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
        # ---------------------------------------------------------------------------
        # _paramSlit[0][0]: slit 1 - distance horizontal
        # _paramSlit[0][1]: slit 1 - distance vertical
        # _paramSlit[0][2]: slit 1 - step
        self._paramSlit = [[None, None, None], [None, None, None]]

        # If should center each slit
        # _centerSlit[0]: slit 1
        self._centerSlit = [False, False]

        # If should scan all the path allowed by each motor axis
        # _fullPathSlit[0]: slit 1
        self._fullPathSlit = [False, False]

    def init(self):
        """
        Descript. :
        """
        self.beamcenter_gen = None

    def setDistanceHorizontal(self, distance_hor, slit):
        try:
            self._paramSlit[(slit -1)][0] = float(distance_hor)
        except ValueError:
            pass

    def setDistanceVertical(self, distance_ver, slit):
        try:
            self._paramSlit[(slit -1)][1] = float(distance_ver)
        except ValueError:
            pass

    def setStep(self, step, slit):
        try:
            self._paramSlit[(slit -1)][2] = float(step)
        except ValueError:
            pass

    def setCenterSlit(self, center, slit):
        self._centerSlit[(slit -1)] = center

    def setFullPathSlit(self, fullPath, slit):
        self._fullPathSlit[(slit -1)] = fullPath


    def _waitEndMovingAndUPdate(self, motor_dmov, motor_rbv, counter, signal_pos_changed, signal_int_changed):
        sleep(0.05)
        while(self.getValue(motor_dmov) == 0):
            self.emit(signal_pos_changed, (self.getValue(motor_rbv), ))
            self.emit(signal_int_changed, (abs(self.getValue(counter)), ))
            sleep(0.1)

    def _moveBaseCheckingPosition(self, motor_rbv, motor_rlv, motor_dmov, counter_val, step, initial_position, max_distance, full_path, signal_set_tab, signal_plot_clear, signal_pos_changed, signal_int_changed, signal_plot):
        # Initialize internal parameters
        max_intensity = None
        pos_max_intensity = None

        self.emit(signal_set_tab)
        self.emit(signal_plot_clear)
        # Check if should get initial value of counter
        if (max_intensity == 0):
            max_intensity = self.getValue(counter_val)

        # Move until physical limit which block movement at other side
        physicalLimit = False
        while(not physicalLimit):
            currentRBV = self.getValue(motor_rbv)

            # Move motor by relative position
            self.setValue(motor_rlv, step)

            sleep(0.05)
            while(self.getValue(motor_dmov) == 0):
                sleep(0.01)

            newRBV = self.getValue(motor_rbv)

            if not full_path:
                reachedLimit = (newRBV >= (initial_position + max_distance))
            else:
                reachedLimit = False
            #
            reachedLimit = reachedLimit or (newRBV == currentRBV)

            if (reachedLimit):
                physicalLimit = True
                continue

            self.emit(signal_pos_changed, (newRBV, ))
            intensity = abs(self.getValue(counter_val))
            self.emit(signal_int_changed, (intensity, ))

            self.emit(signal_plot, (newRBV, intensity,))
            if ((max_intensity == None) or (pos_max_intensity == None) or (intensity > max_intensity)):
                max_intensity = intensity
                pos_max_intensity = self.getValue(motor_rbv)

        return (max_intensity, pos_max_intensity)

    def _centerProcedure(self, timeout=None):

        try:
            for slit in range(2):
                # Check if should center this slit
                if (self._centerSlit[slit]):
                    for axis in range(2):
                        # Procedure to find position where intensity of beam is highest
                        initialPosition = self.getValue(BASE_SLIT[slit][axis][2])

                        if (not self._fullPathSlit[slit]):
                            self.setValue(BASE_SLIT[slit][axis][0], (initialPosition - self._paramSlit[slit][axis]))
                        else:
                            self.setValue(BASE_SLIT[slit][axis][0], (self.getValue(BASE_SLIT[slit][axis][8]) + 0.1))
                        # Wait until movement is done and emit signals to update interface
                        self._waitEndMovingAndUPdate(BASE_SLIT[slit][axis][3], BASE_SLIT[slit][axis][2], COUNTER_VAL[slit], POS_CHANGED_SIGN[slit][axis], INT_CHANGED_SIGN[slit])

                        # Going to distance after initial position...
                        (max_int, pos_max_int) = self._moveBaseCheckingPosition(BASE_SLIT[slit][axis][2],
                            BASE_SLIT[slit][axis][1],
                            BASE_SLIT[slit][axis][3],
                            COUNTER_VAL[slit],
                            self._paramSlit[slit][2],
                            initialPosition,
                            self._paramSlit[slit][axis],
                            self._fullPathSlit[slit],
                            SET_TAB_SIGN[slit][axis],
                            CLEAR_SIGN[slit][axis],
                            POS_CHANGED_SIGN[slit][axis],
                            INT_CHANGED_SIGN[slit],
                            PLOT_SIGN[slit][axis])

                        # Move to the position of maximum intensity
                        if (pos_max_int != None):
                            self.setValue(BASE_SLIT[slit][axis][0], pos_max_int)
                            self._waitEndMovingAndUPdate(BASE_SLIT[slit][axis][3], BASE_SLIT[slit][axis][2], COUNTER_VAL[slit], POS_CHANGED_SIGN[slit][axis], INT_CHANGED_SIGN[slit])
            self.emit('centeringConcluded')
        except TypeError:
            self.emit('errorCentering')
            pass


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
        if (self.beamcenter_gen):
            try:
                # Firstly stop the procedure to center beam
                self.beamcenter_gen.kill()
                # Then stop the motor movement
                for slit in range(2):
                    for axis in range(2):
                        self.setValue(BASE_SLIT[slit][axis][4], 1)
            except:
                print("ERROR! Trying to kill gevent of beam-centering....")
                pass
