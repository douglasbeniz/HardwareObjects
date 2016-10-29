#Last change: 2014.09.04 - Ivars Karpics (EMBL Hamburg)
"""
[Name] BeamSlitBox

[Description]
The BeamSlitBox Hardware Object is used to operate slits.

[Channels] -

[Commands] -

[Emited signals]
- statusChanged
- focModeChanged
- gapLimitsChanged
- gapSizeChanged  

[Functions]
- getShape()
- getStepSizes()
- getMinGaps()
- getMaxGaps()
- getGapLimits()
- changeMotorPos()
- mGroupStatusChanged()
- mGroupPosChanged()
- getGapHor()
- getGapVer()
- setGap()
- stopGapHorChange()
- setFocusingMode()
- focusModeChanged()
- setGapLimits()

[Hardware Objects]      
-----------------------------------------------------------------------
| name         | signals             | functions
|----------------------------------------------------------------------
| MotorsGroup  | mGroupPosChanged    | setMotorPosition()
|              | mGroupStatusChanged | stopMotor()
|           |             | setMotorFocMode()    
|----------------------------------------------------------------------
| BeamFocusing | focusModeChanged    |
-----------------------------------------------------------------------

Example Hardware Object XML file :
==================================
<equipment class="LNLSSlitBox">
    <object href="/lnls/lnls-beam_focus" role="focusing"/>                 - focusing mode equipments
    <object href="/lnls/lnls-motor_slit1_gap_hor" role="slit_gap_hor"/>
    <object href="/lnls/lnls-motor_slit1_gap_ver" role="slit_gap_ver"/>

    <gapH>
       <modesAllowed>['Unfocused', 'Vertical']</modesAllowed> - used modes
       <stepSize>0.0050</stepSize>                   - step size used in spinbox
       <minGap>0.001</minGap>                        - min gap
       <maxGap>2.000</maxGap>                        - max max gap
       <updateTolerance>0.0005</updateTolerance>     - gap update tolerance
    </gapH>
    <gapV>                                              
       <modesAllowed>['Unfocused', 'Horizontal']</modesAllowed>
       <stepSize>0.0050</stepSize>
       <minGap>0.001</minGap>
       <maxGap>2.000</maxGap>
       <updateTolerance>0.0005</updateTolerance>
    </gapV>
</equipment>
"""
import logging
from HardwareRepository.BaseHardwareObjects import Equipment
from HardwareRepository import HardwareRepository

class LNLSSlitBox(Equipment):
    """
    Descript. : User can define sizes of horizontal and verstical slits by 
                entering direct size and pressing Enter or by using up and 
                down buttons. Slits operations are enabled accordingly to 
                the detected focusing mode.
                  - Unfocused beam (both enabled)
                  - Horizontally focused (hor. disabled and ver. enabled)            
                  - Vertically focused (hor. enabled and ver. disabled)
                  - Double focused (both disabled)
                User can stop slit movement by pressing stop button 
                (enabled if slits moves).    
    """    
    def __init__(self, *args):
        """
        Decript. :
        """
        Equipment.__init__(self, *args)

        self.decimal_places = None
        self.active_focus_mode = None
        self.gaps_dict = None
        self.motors_dict = None
        self.init_max_gaps = None
        self.hor_gap = False
        self.ver_gap = False

        # HardwareObjects related to the slit
        self.beam_focus_hwobj = None
        self.slit_gap_hor_hwobj = None
        self.slit_gap_ver_hwobj = None

    def init(self):
        """
        Descript. 
        """
        self.decimal_places = 6
        self.gaps_dict = {}
        self.gaps_dict['Hor'] = self['gapH'].getProperties()
        self.gaps_dict['Ver'] = self['gapV'].getProperties()
        self.gaps_dict['Hor']['value'] = 0.10
        self.gaps_dict['Ver']['value'] = 0.10
        self.gaps_dict['Hor']['status'] = ''
        self.gaps_dict['Ver']['status'] = ''
        self.init_max_gaps = self.get_max_gaps()

        self.motors_dict = {}

        self.beam_focus_hwobj = self.getObjectByRole("focusing")
        if self.beam_focus_hwobj:
            self.connect(self.beam_focus_hwobj, 'definerPosChanged', self.focus_mode_changed)
            self.active_focus_mode = self.beam_focus_hwobj.get_active_focus_mode()
            # 
            self.focus_mode_changed(self.active_focus_mode, )
        else:
            logging.getLogger("HWR").debug('LNLSSlitBox: beamFocus HO not defined')

        self.slit_gap_hor_hwobj = self.getObjectByRole("slit_gap_hor")
        if (self.slit_gap_hor_hwobj is not None):
            self.connect(self.slit_gap_hor_hwobj, 'positionChanged', self.slit_gap_pos_changed)
            self.connect(self.slit_gap_hor_hwobj, 'stateChanged', self.slit_gap_state_changed)

        self.slit_gap_ver_hwobj = self.getObjectByRole("slit_gap_ver")
        if (self.slit_gap_ver_hwobj is not None):
            self.connect(self.slit_gap_ver_hwobj, 'positionChanged', self.slit_gap_pos_changed)
            self.connect(self.slit_gap_ver_hwobj, 'stateChanged', self.slit_gap_state_changed)

    def get_step_sizes(self):
        """
        Descript. : returns Hor and Ver step sizes
        Arguments : -                                        
        Return    : step size values (list of two values)
        """
        return [self.gaps_dict['Hor']['stepSize'], 
                self.gaps_dict['Ver']['stepSize']]

    def get_min_gaps(self):
        """
        Descript. : returns min Hor and Ver gaps values
        Arguments : -                                        
        Return    : min gap values (list of two values)
        """
        return [self.gaps_dict['Hor']['minGap'], 
                self.gaps_dict['Ver']['minGap']]        

    def get_max_gaps(self):
        """
        Descript. : returns max Hor and Ver gaps values
        Arguments : -                                        
        Return    : max gap values (list of two values)
        """
        return [self.gaps_dict['Hor']['maxGap'], 
                self.gaps_dict['Ver']['maxGap']]     

    def get_gap_limits(self, gap_name):
        """
        Descript. : returns gap min and max limits
        Arguments : gap name                                        
        Return    : min and max gap values (list of two values)
        """
        return [self.gaps_dict[gap_name]['minGap'],
                self.gaps_dict[gap_name]['maxGap']]           


    def slit_gap_state_changed(self, new_status):
        """
        Descript. : function called if motors group status is changed
        Arguments : new status (string)                                        
        Return    : -
        """
        self.gaps_dict['Hor']['status'] = self.get_gap_hor_state()
        self.gaps_dict['Ver']['status'] = self.get_gap_ver_state()

        self.emit('statusChanged', (self.gaps_dict['Hor']['status'], 
                                    self.gaps_dict['Ver']['status']))

    def slit_gap_pos_changed(self, new_position):
        """
        Descrip. : function called if one or sever motors value/s are changed
        Arguments: motors values (list of float values)                                     
        Return   : -
        """
        self.gaps_dict['Hor']['value'] = self.get_gap_hor()
        self.gaps_dict['Ver']['value'] = self.get_gap_ver()

        self.emit('gapSizeChanged', [self.gaps_dict['Hor']['value'], 
             self.gaps_dict['Ver']['value']])

    def get_gap_hor(self):
        """
        Descript. : evaluates Horizontal gap
        Arguments : -                                        
        Return    : Hor gap value in mm 
        """
        if (self.slit_gap_hor_hwobj):
            gap = float("%.5f" % self.slit_gap_hor_hwobj.getPosition())
        else:
            gap = 0

        return gap

    def get_gap_hor_state(self):
        """
        Descript. : 
        Arguments : -                                        
        Return    : Hor gap status
        """

        if (self.slit_gap_hor_hwobj):
            state = ('Move' if self.slit_gap_hor_hwobj.isMoving() else 'Ready')
        else:
            state = 'Unknown'

        return state

    def get_gap_ver(self):
        """
        Descript. : evaluates Vertical gap
        Arguments : -                                        
        Return    : Ver gap value in mm
        """
        if (self.slit_gap_ver_hwobj):
            gap =  float("%.5f" % self.slit_gap_ver_hwobj.getPosition())
        else:
            gap = 0

        return gap

    def get_gap_ver_state(self):
        """
        Descript. : 
        Arguments : -                                        
        Return    : Hor gap status
        """

        if (self.slit_gap_ver_hwobj):
            state = ('Move' if self.slit_gap_ver_hwobj.isMoving() else 'Ready')
        else:
            state = 'Unknown'

        return state

    def get_gaps(self):
        """
        Descript.
        """
        return 'Horizontal: %0.3f' % self.get_gap_hor() + \
               ' Vertical: %0.3f' % self.get_gap_ver()
    
    def set_gap(self, gap_name, new_gap):
        """
        Descript. : sets new gap value
        Arguments : gap name(string), gap value(float)                                        
        Return    : -
        """
        if ((gap_name == 'Hor') and (self.slit_gap_hor_hwobj is not None)):
            self.slit_gap_hor_hwobj.move(new_gap)
        elif ((gap_name == 'Ver') and (self.slit_gap_ver_hwobj is not None)):
            self.slit_gap_ver_hwobj.move(new_gap)
        else:
            print("Error! Trying to move %s gap motor..." % gap_name)

    def stop_gap_move(self, gap_name):
        """
        Descript.: stops motors movements
        Arguments: gap name(string)                                        
        Return   : -
        """
        if ((gap_name == 'Hor') and (self.slit_gap_hor_hwobj is not None)):
            self.slit_gap_hor_hwobj.stop()
        elif ((gap_name == 'Ver') and (self.slit_gap_ver_hwobj is not None)):
            self.slit_gap_ver_hwobj.stop()
        else:
            print("Error! Trying to stop %s gap motor..." % gap_name)

    def focus_mode_changed(self, new_focus_mode, size=0):
        """
        Descript. : called if focusing mode is changed
        Arguments : new focusing mode (string)
        Return    : - 
        """
        # LNLS
        # For while, fixed, always enabled
        self.hor_gap = True
        self.ver_gap = True
        self.emit('focusModeChanged', (self.hor_gap, self.ver_gap))

    def set_gaps_limits(self, new_gaps_limits):
        """
        Descript. : sets max gap Limits
        Arguments : [max Hor gap, max Ver gap] (list of two float values)
        Return    : -
        """
        if new_gaps_limits is not None:
            self.gaps_dict['Hor']['maxGap'] = min(self.init_max_gaps[0], new_gaps_limits[0])
            self.gaps_dict['Ver']['maxGap'] = min(self.init_max_gaps[1], new_gaps_limits[1])    
            self.emit('gapLimitsChanged', [self.gaps_dict['Hor']['maxGap'], 
                                           self.gaps_dict['Ver']['maxGap']])

    def update_values(self):
        self.emit('focusModeChanged', (self.hor_gap, self.ver_gap)) 
        self.emit('gapSizeChanged', [self.gaps_dict['Hor']['value'],
                                     self.gaps_dict['Ver']['value']])

