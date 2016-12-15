"""
LNLSBeamCentering.py
"""
import logging
from HardwareRepository.BaseHardwareObjects import Equipment
from time import sleep
import gevent

#------------------------------------------------------------------------------
# Constant names from lnls-beam_center.xml
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

BASE_SLIT = [[['mono2ndXtal_val', 'mono2ndXtal_rlv', 'mono2ndXtal_rbv', 'mono2ndXtal_dmov', 'mono2ndXtal_stop', 'mono2ndXtal_hls', 'mono2ndXtal_lls', 'mono2ndXtal_hlm', 'mono2ndXtal_llm'],
              [ None,              None,              None,              None,               None,               None,              None,              None,              None            ]],
             [['slit1BaseX1_val', 'slit1BaseX1_rlv', 'slit1BaseX1_rbv', 'slit1BaseX1_dmov', 'slit1BaseX1_stop', 'slit1BaseX1_hls', 'slit1BaseX1_lls', 'slit1BaseX1_hlm', 'slit1BaseX1_llm'],
              ['slit1BaseZ1_val', 'slit1BaseZ1_rlv', 'slit1BaseZ1_rbv', 'slit1BaseZ1_dmov', 'slit1BaseZ1_stop', 'slit1BaseZ1_hls', 'slit1BaseZ1_lls', 'slit1BaseZ1_hlm', 'slit1BaseZ1_llm']],
             [['slit2BaseX1_val', 'slit2BaseX1_rlv', 'slit2BaseX1_rbv', 'slit2BaseX1_dmov', 'slit2BaseX1_stop', 'slit2BaseX1_hls', 'slit1BaseX1_lls', 'slit2BaseX1_hlm', 'slit1BaseX1_llm'],
              ['slit2BaseZ1_val', 'slit2BaseZ1_rlv', 'slit2BaseZ1_rbv', 'slit2BaseZ1_dmov', 'slit2BaseZ1_stop', 'slit2BaseZ1_hls', 'slit1BaseZ1_lls', 'slit2BaseZ1_hlm', 'slit1BaseZ1_llm']]]

COUNTER_VAL = ['counterInt_val', 'counter1_val', 'counter2_val']

# Horizontal = X
# Vertical   = Z
POS_CHANGED_SIGN = [['position2ndXtalChanged', None], ['positionHorSlit1Changed', 'positionVerSlit1Changed'], ['positionHorSlit2Changed', 'positionVerSlit2Changed']]
CLEAR_SIGN = [['plotClear2ndXtal', None], ['plotClearHorSlit1', 'plotClearVerSlit1'], ['plotClearHorSlit2', 'plotClearVerSlit2']]
PLOT_SIGN = [['plotNewPoint2ndXtal', None], ['plotNewPointHorSlit1', 'plotNewPointVerSlit1'], ['plotNewPointHorSlit2', 'plotNewPointVerSlit2']]
INT_CHANGED_SIGN = ['intensity2ndXtalChanged', 'intensitySlit1Changed', 'intensitySlit2Changed']
SET_TAB_SIGN = [['setTab2ndXtal', None], ['setTabHorSlit1', 'setTabVerSlit1'], ['setTabHorSlit2', 'setTabVerSlit2']]

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
        self._paramSlit = [[None, None, None], [None, None, None], [None, None, None]]

        # If should center each slit
        # _centerSlit[0]: slit 1
        self._centerSlit = [False, False, False]

        # If should scan all the path allowed by each motor axis
        # _fullPathSlit[0]: slit 1
        self._fullPathSlit = [False, False, False]

    def init(self):
        """
        Descript. :
        """
        self.beamcenter_gen = None

    def setDefaultParams(self):
        # Set default parameters based on XML data
        try:
            self.emit('setDefaultPitchParams', (self.default_angle_pitch, self.default_step_pitch, ))
        except:
            logging.getLogger("HWR").error('LNLSBeamCentering - Error getting some default parameters for Pitch, please check!')

        try:
            for slitNum in range(2):
                self.emit('setDefaultSlitParams', (self.default_hor_distance_slits, self.default_ver_distance_slits, self.default_step_slits, slitNum, ))
        except:
            logging.getLogger("HWR").error('LNLSBeamCentering - Error getting some default parameters for Slits, please check!')

    def setDistanceHorizontal(self, distance_hor, slit):
        try:
            self._paramSlit[(slit -1)][0] = abs(float(distance_hor.replace("," , ".")))
        except ValueError:
            pass

    def setDistanceVertical(self, distance_ver, slit):
        try:
            self._paramSlit[(slit -1)][1] = abs(float(distance_ver.replace("," , ".")))
        except ValueError:
            pass

    def setStep(self, step, slit):
        try:
            self._paramSlit[(slit -1)][2] = abs(float(step.replace("," , ".")))
        except ValueError:
            pass

    def setCenterSlit(self, center, slit):
        self._centerSlit[(slit -1)] = center

    def setFullPathSlit(self, fullPath, slit):
        self._fullPathSlit[(slit -1)] = fullPath


    def _waitEndMovingAndUPdate(self, motor_dmov, motor_rbv, counter, counter_factor, signal_pos_changed, signal_int_changed):
        sleep(0.05)

        while(self.getValue(motor_dmov) == 0):
            self.emit(signal_pos_changed, (self.getValue(motor_rbv), ))
            self.emit(signal_int_changed, ('%.3E' % (float(self.getValue(counter)) * counter_factor), ))
            sleep(0.1)

        # Just to be sure we will present the latest valid value....
        self.emit(signal_pos_changed, (self.getValue(motor_rbv), ))
        self.emit(signal_int_changed, ('%.3E' % (float(self.getValue(counter)) * counter_factor), ))

    def _moveBaseCheckingPosition(self, motor_rbv, motor_rlv, motor_dmov, counter_val, counter_factor, step, initial_position, max_distance, full_path, signal_set_tab, signal_plot_clear, signal_pos_changed, signal_int_changed, signal_plot):
        # Initialize internal parameters
        max_intensity = None
        pos_max_intensity = None
        # Set the maximum number of tries to move the motors
        max_move_tries = 15

        self.emit(signal_set_tab)
        self.emit(signal_plot_clear)

        # This is to consider the first point...
        currentRBV = self.getValue(motor_rbv)
        self.emit(signal_pos_changed, (currentRBV, ))
        intensity_show = '%.3E' % (float(self.getValue(counter_val)) * counter_factor)
        intensity = float(self.getValue(counter_val)) * counter_factor
        self.emit(signal_int_changed, (intensity_show, ))
        self.emit(signal_plot, (currentRBV, intensity,))

        # Store the first position and intensity as the initial ones
        max_intensity = intensity
        pos_max_intensity = currentRBV

        # Move until physical limit which block movement at other side
        physicalLimit = False
        reachedLimit = False

        while(not reachedLimit):

            currentRBV = self.getValue(motor_rbv)
            # Move motor by relative position
            self.setValue(motor_rlv, step)

            # Initialize newRBV
            newRBV = currentRBV
            move_try = 0

            while((move_try < max_move_tries) and (newRBV == currentRBV)):
                sleep(0.05)
                while(self.getValue(motor_dmov) == 0):
                    sleep(0.01)

                newRBV = self.getValue(motor_rbv)
                move_try += 1 

            if not full_path:
                reachedMaxDistance = (newRBV >= (initial_position + max_distance)) or ((newRBV + step) >= (initial_position + max_distance))
            else:
                reachedMaxDistance = False

            #
            physicalLimit = (newRBV == currentRBV)

            self.emit(signal_pos_changed, (newRBV, ))
            intensity_show = '%.3E' % (float(self.getValue(counter_val)) * counter_factor)
            intensity = float(self.getValue(counter_val)) * counter_factor
            self.emit(signal_int_changed, (intensity_show, ))
            self.emit(signal_plot, (newRBV, intensity,))

            if (intensity > max_intensity):
                max_intensity = intensity
                pos_max_intensity = newRBV

            if (reachedMaxDistance or physicalLimit):
                reachedLimit = True
                continue

        return (max_intensity, pos_max_intensity, (False if full_path else physicalLimit))

    def _centerProcedure(self, timeout=None):

        try:
            for slit in range(3):
                # Check if should center this slit
                if (self._centerSlit[slit]):
                    for axis in range(2):
                        if (self._fullPathSlit[slit] or (self._paramSlit[slit][axis] is not None and self._paramSlit[slit][axis] != 0)):
                            if (BASE_SLIT[slit][axis][2] is not None):
                                # Procedure to find position where intensity of beam is highest
                                initialPosition = self.getValue(BASE_SLIT[slit][axis][2])

                                if (not self._fullPathSlit[slit]):
                                    self.setValue(BASE_SLIT[slit][axis][0], (initialPosition - abs(self._paramSlit[slit][axis])))
                                else:
                                    #self.setValue(BASE_SLIT[slit][axis][0], (self.getValue(BASE_SLIT[slit][axis][8]) + 0.1))
                                    self.setValue(BASE_SLIT[slit][axis][0], (self.getValue(BASE_SLIT[slit][axis][8])))

                                # Wait until movement is done and emit signals to update interface
                                self._waitEndMovingAndUPdate(BASE_SLIT[slit][axis][3], BASE_SLIT[slit][axis][2], COUNTER_VAL[slit], (-1 if (slit == 0) else 1), POS_CHANGED_SIGN[slit][axis], INT_CHANGED_SIGN[slit])

                                # Going to distance after initial position...
                                (max_int, pos_max_int, phys_limit) = self._moveBaseCheckingPosition(BASE_SLIT[slit][axis][2],
                                    BASE_SLIT[slit][axis][1],
                                    BASE_SLIT[slit][axis][3],
                                    COUNTER_VAL[slit],
                                    -1 if (slit == 0) else 1,       # Bias voltage of counter for Rocking is inverted
                                    self._paramSlit[slit][2],
                                    initialPosition,
                                    0 if self._paramSlit[slit][axis] is None else abs(self._paramSlit[slit][axis]),
                                    self._fullPathSlit[slit],
                                    SET_TAB_SIGN[slit][axis],
                                    CLEAR_SIGN[slit][axis],
                                    POS_CHANGED_SIGN[slit][axis],
                                    INT_CHANGED_SIGN[slit],
                                    PLOT_SIGN[slit][axis])

                                if (phys_limit):
                                    self.emit('limitReached')

                                # Move to the position of maximum intensity
                                if (pos_max_int != None):
                                    self.setValue(BASE_SLIT[slit][axis][0], pos_max_int)
                                    self._waitEndMovingAndUPdate(BASE_SLIT[slit][axis][3], BASE_SLIT[slit][axis][2], COUNTER_VAL[slit], (-1 if (slit == 0) else 1), POS_CHANGED_SIGN[slit][axis], INT_CHANGED_SIGN[slit])
            self.emit('centeringConcluded')
        except TypeError:
            self.emit('errorCentering')
            pass


    def start(self):
        """
        Descript. : 
        """
        validStep = True

        # Check if steps are valids
        for slit in range(3):
            if (self._centerSlit[slit] and not self._paramSlit[slit][2]):
                validStep = False

            if (self._paramSlit[slit][0] is not None and self._paramSlit[slit][0] > 0 and self._paramSlit[slit][2] is not None and (self._paramSlit[slit][2] > self._paramSlit[slit][0])):
                validStep = False

            if (self._paramSlit[slit][1] is not None and self._paramSlit[slit][1] > 0 and self._paramSlit[slit][2] is not None and (self._paramSlit[slit][2] > self._paramSlit[slit][1])):
                validStep = False

        if (validStep):
            # Start a new thread to run centering...
            self.beamcenter_gen = gevent.spawn(self._centerProcedure, 0.1)
        else:
            self.emit('errorStep')

    def cancel(self):
        """
        Descript. : 
        """
        if (self.beamcenter_gen):
            try:
                # Firstly stop the procedure to center beam
                self.beamcenter_gen.kill()
                # Then stop the motor movement
                for slit in range(3):
                    for axis in range(2):
                        self.setValue(BASE_SLIT[slit][axis][4], 1)
            except:
                print("ERROR! Trying to kill gevent of beam-centering....")
                pass
