"""
LNLSBeamFocus.py
"""
import logging
from HardwareRepository.BaseHardwareObjects import Equipment
from time import sleep

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
# BASE SLIT X2
BASE_SLIT_X2_VAL = 'epicsSlitBaseX2_val'
BASE_SLIT_X2_RLV = 'epicsSlitBaseX2_rlv'
BASE_SLIT_X2_RBV = 'epicsSlitBaseX2_rbv'
BASE_SLIT_X2_DMOV = 'epicsSlitBaseX2_dmov'
BASE_SLIT_X2_STOP = 'epicsSlitBaseX2_stop'
BASE_SLIT_X2_HLS = 'epicsSlitBaseX2_hls'
BASE_SLIT_X2_LLS = 'epicsSlitBaseX2_lls'
# KEITHLEY 6517A
K6517A_VAL = 'epicsKeithley6517A_measure'

#------------------------------------------------------------------------------
class LNLSBeamFocus(Equipment):
    """
    Descript. :
    """
    def __init__(self, name):
        """
        Descript. :
        """
        Equipment.__init__(self, name) 
        self.active_focus_mode = None
        self.size = [9999, 9999]
        self.focus_modes = None
        self.focus_motors_dict = None
        self.motors_groups = []

        self.cmd_set_calibration_name = None
        self.cmd_set_phase = None 

    def init(self):
        """
        Descript. :
        """
        self.focus_modes = [] 
        for focus_mode in self['focusModes']:
            self.focus_modes.append({'modeName': focus_mode.modeName, 
                                     'size': float(focus_mode.size), 
                                     'message': focus_mode.message,
                                     'diverg': float(focus_mode.divergence)})
        self.focus_motors_dict = {} 

        focus_motors = []
        try: 
           focus_motors = eval(self.getProperty('focusMotors'))
        except:
           pass
      
        for focus_motor in focus_motors:
            self.focus_motors_dict[focus_motor] = []
       
        self.motors_groups = self.getDevices()
        if len(self.motors_groups) > 0:
            for motors_group in self.motors_groups:
                self.connect(motors_group, 'mGroupFocModeChanged', 
                     self.motor_group_focus_mode_changed)
        else:
            logging.getLogger("HWR").debug('BeamFocusing: No motors defined') 
            self.active_focus_mode = self.focus_modes[0]['modeName'] 
            self.size = self.focus_modes[0]['size']
            self.update_values()
        
        self.cmd_set_calibration_name = self.getCommandObject('cmdSetCallibrationName')
        try:
           self.cmd_set_phase = eval(self.getProperty('setPhaseCmd'))
        except:
           pass 

    def get_focus_motors(self):
        """
        Descript. :
        """ 
        focus_motors = []
        if self.motors_groups is not None:
            for motors_group in self.motors_groups:
                motors_group_list = motors_group.get_motors_dict()
                for motor in motors_group_list:
                    focus_motors.append(motor)
        return focus_motors

    def motor_group_focus_mode_changed(self, value):
        """
        Descript. : called if motors group focusing is changed 
        Arguments : new focus mode name(string                                 
        Return    : -
        """
        motors_group_foc_mode = eval(value)
        for motor in motors_group_foc_mode:
            if motor in self.focus_motors_dict:
                self.focus_motors_dict[motor] = motors_group_foc_mode[motor]

        prev_mode = self.active_focus_mode
        self.active_focus_mode, self.size = self.get_active_focus_mode()
        
        if prev_mode != self.active_focus_mode:
            self.emit('definerPosChanged', (self.active_focus_mode, self.size))
            if self.cmd_set_calibration_name and self.active_focus_mode:
                self.cmd_set_calibration_name(self.active_focus_mode.lower())

        print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')
        print('motor_group_focus_mode_changed')
        print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')

    def get_focus_mode_names(self):
        """
        Descript. : returns defined focus modes names 
        Arguments : -                                        
        Return    : focus mode names (list of strings)
        """
        names = []
        for focus_mode in self.focus_modes:
            names.append(focus_mode['modeName'])
        return names

    def get_focus_mode_message(self, focus_mode_name):
        """
        Descript. : returns foc mode message
        Arguments : mode name (string)                                        
        Return    : message (string)
        """
        for focus_mode in self.focus_modes:
            if focus_mode['modeName'] == focus_mode_name:
                message = focus_mode['message']
                return message

    def get_active_focus_mode(self):
        """
        Descript. : evaluate and get active foc mode
        Arguments : -                                        
        Return    : mode name (string or None if unable to detect)
        """
        if len(self.focus_motors_dict) > 0:
            active_focus_mode = None
            for focus_mode in self.focus_modes:
                self.size = focus_mode['size']
                active_focus_mode = focus_mode['modeName']
                for motor in self.focus_motors_dict:
                    if len(self.focus_motors_dict[motor]) == 0:
                        active_focus_mode = None
                        self.size = [9999, 9999]
                    elif active_focus_mode not in \
                        self.focus_motors_dict[motor]:
                        active_focus_mode = None
                        self.size = [9999, 9999]
                        break
                if active_focus_mode is not None:
                    break
            if active_focus_mode != self.active_focus_mode:
                self.active_focus_mode = active_focus_mode  
                logging.getLogger("HWR").info('Focusing: %s mode detected' %active_focus_mode)
        return self.active_focus_mode, self.size

    def get_focus_mode(self):
        """
        Descript. :
        """
        if self.active_focus_mode:
            return self.active_focus_mode.lower()

    def set_motor_focus_mode(self, motor_name, focus_mode): 
        """
        Descript. :
        """ 
        if focus_mode is not None:
            for motor in self.motors_groups:
                motor.set_motor_focus_mode(motor_name, focus_mode)

        print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')
        print('set_motor_focus_mode')
        print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')

    def set_focus_mode(self, focus_mode):
        """
        Descript. : sets focusing mode
        Arguments : new mode name (string)                                        
        Return    : -
        """
        if focus_mode and self.cmd_set_phase:
            #tinequery(self.cmd_set_phase['address'], 
            #          self.cmd_set_phase['property'], 
            #          self.cmd_set_phase['argument'])
            if self.motors_groups:       
                for motors_group in self.motors_groups:
                    motors_group.set_motor_group_focus_mode(focus_mode)
        else:
            #No motors defined
            self.active_focus_mode = focus_mode

        print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')
        print('set_focus_mode')
        print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')

        if (focus_mode == 'Focused'):
            # Procedure to find position where intensity of beam is highest

            max_intensity_horizontal = 0
            pos_max_intensity_hor = 0

            # Move until physical limit which block movement at one side
            physicalLimit = False
            while(not physicalLimit):
                currentRBV = self.getValue(BASE_SLIT_X1_RBV)
                self.setValue(BASE_SLIT_X1_RLV, -0.05)
                sleep(0.2)
                if (self.getValue(BASE_SLIT_X1_RBV) == currentRBV):
                    physicalLimit = True
                    continue
                intensity = self.getValue(K6517A_VAL)
                if (intensity > max_intensity_horizontal):
                    pos_max_intensity_hor = self.getValue(BASE_SLIT_X1_RBV)

            # Move until physical limit which block movement at other side
            physicalLimit = False
            while(not physicalLimit):
                currentRBV = self.getValue(BASE_SLIT_X1_RBV)
                self.setValue(BASE_SLIT_X1_RLV, 0.05)
                sleep(0.2)
                if (self.getValue(BASE_SLIT_X1_RBV) == currentRBV):
                    physicalLimit = True
                    continue
                intensity = self.getValue(K6517A_VAL)
                if (intensity > max_intensity_horizontal):
                    pos_max_intensity_hor = self.getValue(BASE_SLIT_X1_RBV)

            # Move to the position of maximum intensity
            self.setValue(BASE_SLIT_X1_VAL, pos_max_intensity_hor)

            # Doing the same at vertical...

            max_intensity_vertical = 0
            pos_max_intensity_ver = 0

            # Move until physical limit which block movement at one side
            physicalLimit = False
            while(not physicalLimit):
                currentRBV = self.getValue(BASE_SLIT_X2_RBV)
                self.setValue(BASE_SLIT_X2_RLV, -0.05)
                sleep(0.2)
                if (self.getValue(BASE_SLIT_X2_RBV) == currentRBV):
                    physicalLimit = True
                    continue
                intensity = self.getValue(K6517A_VAL)
                if (intensity > max_intensity_horizontal):
                    pos_max_intensity_hor = self.getValue(BASE_SLIT_X2_RBV)

            # Move until physical limit which block movement at other side
            physicalLimit = False
            while(not physicalLimit):
                currentRBV = self.getValue(BASE_SLIT_X2_RBV)
                self.setValue(BASE_SLIT_X2_RLV, 0.05)
                sleep(0.2)
                if (self.getValue(BASE_SLIT_X2_RBV) == currentRBV):
                    physicalLimit = True
                    continue
                intensity = self.getValue(K6517A_VAL)
                if (intensity > max_intensity_horizontal):
                    pos_max_intensity_hor = self.getValue(BASE_SLIT_X2_RBV)

            # Move to the position of maximum intensity
            self.setValue(BASE_SLIT_X2_VAL, pos_max_intensity_hor)

            print("End of centering focus!")

    def get_divergence_hor(self):
        """
        Descript. :
        """
        for focus_mode in self.focus_modes:
            if focus_mode['modeName'] == self.active_focus_mode:
                return focus_mode['diverg'][0]

    def get_divergence_ver(self):
        """
        Descript. :
        """
        for focus_mode in self.focus_modes:
            if focus_mode['modeName'] == self.active_focus_mode:
                return focus_mode['diverg'][1]

    def update_values(self):
        self.emit('definerPosChanged', (self.active_focus_mode, self.size))
