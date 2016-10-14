#
#  Project: MXCuBE
#  https://github.com/mxcube.
#
#  This file is part of MXCuBE software.
#
#  MXCuBE is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  MXCuBE is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#  along with MXCuBE.  If not, see <http://www.gnu.org/licenses/>.

import os
import copy
import time
import math
import logging
import tempfile
import gevent
import random

try:
   import lucid2
except:
   pass

import queue_model_objects_v1 as qmo

from GenericDiffractometer import GenericDiffractometer
from gevent.event import AsyncResult


last_centred_position = [200, 200]

OMEGA_VELO_CENTRING = 1.5

#--------------------------------------------------------------------------------
#
class LNLSGoniometer(GenericDiffractometer):
    """
    Descript. :
    """

    def __init__(self, *args):
        """
        Descript. :
        """
        GenericDiffractometer.__init__(self, *args)

        self.phiMotor = None
        self.phizMotor = None
        self.phiyMotor = None
        self.lightMotor = None
        self.zoomMotor = None
        self.sampleXMotor = None
        self.sampleYMotor = None
        self.camera = None
        self._drawing = None

        self.takeSnapshots = self.take_snapshots

        self.connect(self, 'equipmentReady', self.equipmentReady)
        self.connect(self, 'equipmentNotReady', self.equipmentNotReady)

    def init(self):
        """
        Descript. :
        """
        GenericDiffractometer.init(self)

        self.pixels_per_mm_x = 85       # 85 pixels / 1mm for 0.5 zoom
        self.pixels_per_mm_y = 85       # 85 pixels / 1mm for 0.5 zoom
        
        self.cancel_centring_methods = {}
        self.current_positions_dict = {'phiy'  : 0, 'phiz' : 0, 'sampx' : 0,
                                       'sampy' : 0, 'zoom' : 0, 'phi' : 17.6,
                                       'focus' : 0, 'kappa': 0, 'kappa_phi': 0,
                                       'beam_x': 0, 'beam_y': 0} 
        self.current_state_dict = {}
        self.centring_status = {"valid": False}
        self.centring_time = 0

        # Parameters from XML configuration
        self.image_width = self.defaultImageWidth
        self.image_height = self.defaultImageHeight

        self.equipmentReady()

        # ---------------------------------------------------------------------
        # Beam-info
        self.beam_info_hwobj = self.getObjectByRole("beam_info")

        if (self.beam_info_hwobj):
            self.beam_position = self.beam_info_hwobj.get_beam_position()
        else:
            self.beam_position = [self.image_width/2, self.image_height/2]

        # ---------------------------------------------------------------------
        # Camera
        self.camera_hwobj = self.getObjectByRole("camera")

        # ---------------------------------------------------------------------
        # Motors
        self.motor_omega_hwobj = self.getObjectByRole("omega")
        self.motor_goniox_hwobj = self.getObjectByRole("goniox")
        self.motor_sampx_hwobj = self.getObjectByRole("sampx")
        self.motor_sampy_hwobj = self.getObjectByRole("sampy")
        # Zoom
        self.motor_zoom_hwobj = self.getObjectByRole("zoom")

        self.reversing_rotation = self.getProperty("reversingRotation")
        try:
            self.grid_direction = eval(self.getProperty("gridDirection"))
        except:
            self.grid_direction = {"fast": (0, 1), "slow": (1, 0)}

        try:
            self.phase_list = eval(self.getProperty("phaseList"))
        except:
            self.phase_list = ['demo']

        # Attributes used by snapshot
        self.snapshotFilePath = None
        self.snapshotFilePrefix = None
        self.collectStartOscillation = None
        self.collectEndOscillation = None

        # Methods exported
        self.takeSnapshots = self.take_snapshots
        self.getPositions = self.get_positions

    def set_drawing(self, drawing):
        self._drawing = drawing

    def set_snapshot_file_path(self, path):
        self.snapshotFilePath = path

    def set_snapshot_file_prefix(self, prefix):
        self.snapshotFilePrefix = prefix

    def set_collect_oscillation_interval(self, start, end):
        self.collectStartOscillation = start
        self.collectEndOscillation = end

    def getStatus(self):
        """
        Descript. :
        """
        return "ready"

    def in_plate_mode(self):
        return True

    def is_reversing_rotation(self):
        return True

    def get_grid_direction(self):
        """
        Descript. :
        """
        return self.grid_direction

    def move_omega_absolute(self, absolute_position):
        self.motor_omega_hwobj.move(absolute_position)

    # initial_angle in degrees
    def move_omega_initial_angle(self, initial_angle):
        # Store previous Omega velocity
        _previous_omega_velo = self.get_omega_velocity()

        # Set velocity of omega to move during starting
        self.set_omega_velocity(OMEGA_VELO_CENTRING)

        # Move to initial angle
        self.motor_omega_hwobj.move(initial_angle, wait=True)

        # Restore previous velocity
        self.set_omega_velocity(_previous_omega_velo)

    # Velocity in RPM
    def set_omega_velocity(self, velocity):
        self.motor_omega_hwobj.setVelocity(velocity)

    def get_omega_velocity(self):
        return self.motor_omega_hwobj.getVelocity()

    def manual_centring(self):
        """
        Descript. :
        """
        # Set velocity of omega to move during centring
        self.set_omega_velocity(OMEGA_VELO_CENTRING)

        # Set scale of pixels per mm according to current zoom
        self.pixels_per_mm_x = self.motor_zoom_hwobj.getPixelsPerMm(0)
        self.pixels_per_mm_y = self.motor_zoom_hwobj.getPixelsPerMm(1)

        # Get clicked position of mouse pointer
        self.user_clicked_event = AsyncResult()
        x, y = self.user_clicked_event.get()
        last_centred_position[0] = x
        last_centred_position[1] = y

        # Get current vallue of involved motors
        omegaPos = self.motor_omega_hwobj.getPosition()
        gonioxPos = self.motor_goniox_hwobj.getPosition()
        sampxPos = self.motor_sampx_hwobj.getPosition()
        sampyPos = self.motor_sampy_hwobj.getPosition()

        # Pixels to move axis X of whole goniometer
        moveGonioX = (self.beam_position[0] - last_centred_position[0])
        # mm to move
        moveGonioX = moveGonioX / self.pixels_per_mm_x

        # Move absolute
        moveGonioX += gonioxPos

        # Calculate new position of X
        moveSampX = (math.cos(math.radians(omegaPos)) * (self.beam_position[1] - float(last_centred_position[1])))
        moveSampX = moveSampX / self.pixels_per_mm_x
        # Move absolute
        moveSampX += sampxPos

        # Calculate new position of Y
        moveSampY = (math.sin(math.radians(omegaPos)) * (self.beam_position[1] - float(last_centred_position[1])))
        moveSampY = moveSampY / self.pixels_per_mm_y
        # Move absolute
        moveSampY += sampyPos

        centred_pos_dir = { 'goniox': moveGonioX, 'sampx': moveSampX, 'sampy': moveSampY }

        return centred_pos_dir

    def is_ready(self):
        """
        Descript. :
        """ 
        return True

    def isValid(self):
        """
        Descript. :
        """
        return True

    def equipmentReady(self):
        """
        Descript. :
        """
        self.emit('minidiffReady', ())

    def equipmentNotReady(self):
        """
        Descript. :
        """
        self.emit('minidiffNotReady', ())

    def phi_motor_moved(self, pos):
        """
        Descript. :
        """
        self.current_positions_dict["phi"] = pos
        self.emit_diffractometer_moved()
        self.emit("phiMotorMoved", pos)
        #self.emit('stateChanged', (self.current_state_dict["phi"], ))

    def phi_motor_state_changed(self, state):
        """
        Descript. :
        """
        self.current_state_dict["phi"] = state
        self.emit('stateChanged', (state, ))

    def invalidate_centring(self):
        """
        Descript. :
        """
        if self.current_centring_procedure is None and self.centring_status["valid"]:
            self.centring_status = {"valid":False}
            self.emitProgressMessage("")
            self.emit('centringInvalid', ())

    def get_centred_point_from_coord(self, x, y, return_by_names=None):
        """
        Descript. :
        """
        """
        random_num = random.random() 
        centred_pos_dir = {'phiy': random_num * 10, 'phiz': random_num,
                          'sampx': 0.0, 'sampy': 9.3, 'zoom': 8.53,
                          'phi': 311.1, 'focus': -0.42, 'kappa': 0.0009,
                          'kappa_phi': 311.0}
        return centred_pos_dir
        """
        return "Not implemented"

    def get_calibration_data(self, offset):
        """
        Descript. :
        """
        return (1.0 / self.x_calib, 1.0 / self.y_calib)

    def refresh_omega_reference_position(self):
        """
        Descript. :
        """
        return

    def get_omega_axis_position(self):  
        """
        Descript. :
        """
        return self.current_positions_dict.get("phi")     

    def beam_position_changed(self, value):
        """
        Descript. :
        """
        self.beam_position = value
  
    def get_current_centring_method(self):
        """
        Descript. :
        """ 
        return self.current_centring_method

    def motor_positions_to_screen(self, centred_positions_dict):
        """
        Descript. :
        """ 
        return last_centred_position[0], last_centred_position[1]

    def moveToCentredPosition(self, centred_position, wait = False):
        """
        Descript. :
        """
        try:
            return self.move_to_centred_position(centred_position, wait = wait)
        except:
            logging.exception("Could not move to centred position")

    def get_positions(self):
        """
        Descript. :
        """

        """
        random_num = random.random()
        return {"phi": random_num * 10, "focus": random_num * 20, 
                "phiy" : -1.07, "phiz": -0.22, "sampx": 0.0, "sampy": 9.3,
                "kappa": 0.0009, "kappa_phi": 311.0, "zoom": 8.53}
        """
        omegaPos = self.motor_omega_hwobj.getPosition()
        gonioxPos = self.motor_goniox_hwobj.getPosition()
        sampxPos = self.motor_sampx_hwobj.getPosition()
        sampyPos = self.motor_sampy_hwobj.getPosition()

        return { "omega": omegaPos, "goniox": gonioxPos, "sampx": sampxPos, "sampy": sampyPos }

    def refresh_video(self):
        """
        Descript. :
        """
        self.emit("minidiffStateChanged", 'testState')
        if self.beam_info_hwobj: 
            self.beam_info_hwobj.beam_pos_hor_changed(320) 
            self.beam_info_hwobj.beam_pos_ver_changed(256)

    def start_auto_focus(self): 
        """
        Descript. :
        """
        return 
  
    def move_to_beam(self, x, y):
        """
        Descript. :
        """
        return

    def start_move_to_beam(self, coord_x=None, coord_y=None, omega=None):
        print("LNLSGoniometer - start_move_to_beam")
        """
        Descript. :
        """
        self.centring_time = time.time()
        curr_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.centring_status = {"valid": True,
                                "startTime": curr_time,
                                "endTime": curr_time} 
        motors = self.get_positions()
        motors["beam_x"] = 0.1
        motors["beam_y"] = 0.1
        self.centring_status["motors"] = motors
        self.centring_status["valid"] = True
        self.centring_status["angleLimit"] = False
        self.emit_progress_message("")
        self.accept_centring()
        self.current_centring_method = None
        self.current_centring_procedure = None  

    def update_values(self):
        self.emit('zoomMotorPredefinedPositionChanged', None, None)
        #omega_ref = [205, 0]
        #self.emit('omegaReferenceChanged', omega_ref)

    def take_snapshots_procedure(self, image_count):
        """
        Descript. :
        """
        # Avoiding a processing of AbstractMultiCollect class for saving snapshots
        #centred_images = []
        centred_images = None
        positions = []

        if (self.camera_hwobj):
            # Calculate goniometer positions where to take snapshots
            if (self.collectEndOscillation is not None and self.collectStartOscillation is not None):
                interval = (self.collectEndOscillation - self.collectStartOscillation)
            else:
                interval = 0

            # To increment in angle increment
            increment = 0 if ((image_count -1) == 0) else (interval / (image_count -1))

            for incrementPos in range(image_count):
                if (self.collectStartOscillation is not None):
                    positions.append(self.collectStartOscillation + (incrementPos * increment))
                else:
                    positions.append(self.motor_omega_hwobj.getPosition())

            for index in range(image_count):
                logging.getLogger("HWR").info("%s - taking snapshot #%d" % (self.__class__.__name__, index + 1))

                while (self.motor_omega_hwobj.getPosition() < positions[index]):
                    gevent.sleep(0.02)

                # Save snapshot image file
                imageFileName = os.path.join(self.snapshotFilePath, self.snapshotFilePrefix + "_" + str(round(self.motor_omega_hwobj.getPosition(),2)) + "_degrees_snapshot.png")

                imageInfo = self.camera_hwobj.takeSnapshot(imageFileName)

                #centred_images.append((0, str(imageInfo)))
                #centred_images.reverse() 
        else:
            logging.getLogger("HWR").exception("%s - could not take crystal snapshots" % (self.__class__.__name__))

        return centred_images

    def take_snapshots(self, image_count, wait=False):
        """
        Descript. :
        """
        if image_count > 0:
            snapshots_procedure = gevent.spawn(self.take_snapshots_procedure, image_count)

            self.emit('centringSnapshots', (None,))
            self.emit_progress_message("Taking snapshots")

            self.centring_status["images"] = []

            snapshots_procedure.link(self.snapshots_done)

            if wait:
                self.centring_status["images"] = snapshots_procedure.get()

    def snapshots_done(self, snapshots_procedure):
        """
        Descript. :
        """
        try:
            self.centring_status["images"] = snapshots_procedure.get()
        except:
            logging.getLogger("HWR").exception("%s - could not take crystal snapshots" % (self.__class__.__name__))
            self.emit('centringSnapshots', (False,))
            self.emit_progress_message("")
        else:
            self.emit('centringSnapshots', (True,))
            self.emit_progress_message("")
        self.emit_progress_message("Sample is centred!")