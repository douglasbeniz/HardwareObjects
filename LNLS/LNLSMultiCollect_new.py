from HardwareRepository.BaseHardwareObjects import HardwareObject
from AbstractMultiCollect import *

import logging
import time
import os
import re
import http.client
import math
import gevent
import glob
import shutil

from sh import rsync


MAXIMUM_TRIES_COPY_CBF    = 500     # 500 * 0.01 seg = 5.00 seg (at most) waiting for CBF creation
MAXIMUM_TRIES_AD_PILATUS  = 120     # 120 * 0.5 = 60 seconds; 1 minute
MAXIMUM_TRIES_CLOSE_SHUTTER  = 200     # 200 * 0,2 = 40 seconds

class LNLSMultiCollect(AbstractMultiCollect, HardwareObject):
    def __init__(self, name):
        AbstractMultiCollect.__init__(self)
        HardwareObject.__init__(self, name)
        self._centring_status = None
        self.ready_event = None
        self.actual_frame_num = 0

    def execute_command(self, command_name, *args, **kwargs): 
        return

    def init(self):
        # ------------------------------------------------------------------
        # This class attributes
        # ------------------------------------------------------------------
        self._previous_omega_velo = None
        self._total_angle = None
        self._total_time = None
        self._total_time_readout = None
        self._initial_angle = None
        self._file_directory = None
        self._snapshot_directory = None
        self._log_directory = None
        self._file_prefix = None
        self._file_run_number = None
        self._image_directory = None
        self._snapshot_camserver_number = None
        self._shutter_control_gen = None
        self._stop_procedure_gen = None

        # ------------------------------------------------------------------
        # Hardware Objects
        # ------------------------------------------------------------------
        self.diffractometer_hwobj = self.getObjectByRole("diffractometer")
        self.camera_hwobj = self.getObjectByRole("camera")
        self.lims_client_hwobj = self.getObjectByRole("lims_client")
        self.machine_current_hwobj = self.getObjectByRole("machine_current")
        self.energy_hwobj = self.getObjectByRole("energy")
        self.resolution_hwobj = self.getObjectByRole("resolution")
        self.transmission_hwobj = self.getObjectByRole("transmission")
        self.detector_hwobj = self.getObjectByRole("detector")
        self.beam_info_hwobj = self.getObjectByRole("beam_info")
        self.autoprocessing_hwobj = self.getObjectByRole("auto_processing")
        self.shutter_hwobj = self.getObjectByRole("safety_shutter")
        self.motor_omega_hwobj = self.getObjectByRole("omega")

        self.setControlObjects(diffractometer = self.getObjectByRole("diffractometer"),
                               sample_changer = self.getObjectByRole("sample_changer"),
                               lims = self.getObjectByRole("dbserver"),
                               safety_shutter = self.getObjectByRole("safety_shutter"),
                               machine_current = self.getObjectByRole("machine_current"),
                               cryo_stream = self.getObjectByRole("cryo_stream"),
                               energy = self.getObjectByRole("energy"),
                               resolution = self.getObjectByRole("resolution"),
                               detector_distance = self.getObjectByRole("detector_distance"),
                               transmission = self.getObjectByRole("transmission"),
                               undulators = self.getObjectByRole("undulators"),
                               flux = self.getObjectByRole("flux"),
                               detector = self.getObjectByRole("detector"),
                               beam_info = self.getObjectByRole("beam_info"))

        undulators = []
        try:
           for undulator in self["undulators"]:
               undulators.append(undulator)
        except:
           pass

        self.setBeamlineConfiguration(synchrotron_name = "LNLS",
                                         directory_prefix = self.getProperty("directory_prefix"),
                                         default_exposure_time = self.detector_hwobj.getProperty("default_exposure_time"),
                                         minimum_exposure_time = self.detector_hwobj.getProperty("minimum_exposure_time"),
                                         detector_fileext = self.detector_hwobj.getProperty("fileSuffix"),
                                         detector_type = self.detector_hwobj.getProperty("type"),
                                         detector_manufacturer = self.detector_hwobj.getProperty("manufacturer"),
                                         detector_model = self.detector_hwobj.getProperty("model"),
                                         detector_px = self.detector_hwobj.getProperty("px"),
                                         detector_py = self.detector_hwobj.getProperty("py"),
                                         undulators = undulators,
                                         focusing_optic = self.getProperty('focusing_optic'),
                                         monochromator_type = self.getProperty('monochromator'),
                                         beam_divergence_vertical = self.beam_info_hwobj.get_beam_divergence_hor(),
                                         beam_divergence_horizontal = self.beam_info_hwobj.get_beam_divergence_ver(),
                                         polarisation = self.getProperty('polarisation'),
                                         input_files_server = self.getProperty("input_files_server"))

        self.emit("collectConnected", (True,))
        self.emit("collectReady", (True, ))


    def do_collect(self, owner, data_collect_parameters):
        # ----------------------------------------------------------------------
        # First of all, check if CamServer is running, otherwise try to start it
        # ----------------------------------------------------------------------
        if (not self.detector_hwobj.is_camserver_connected()):
            error_message =  "CamServer is not running... Trying to start it... Please, wait a while (at most 1 minute)..."
            logging.getLogger("user_level_log").error(error_message)

            # Start a process to initialize CanServer
            self.detector_hwobj.start_camserver_if_not_connected()

            # Check if it started...
            tries = 0
            while ((not self.detector_hwobj.is_camserver_connected() or self.detector_hwobj.is_starting_camserver()) and tries < MAXIMUM_TRIES_AD_PILATUS):
                gevent.sleep(0.5)
                tries += 1

            # If was not started, raise an exception
            if (not self.detector_hwobj.is_camserver_connected()):
                error_message =  "It is impossible to perform an acquisition without \'camserver\' running! Try again or contact beamline staff!"
                logging.getLogger("user_level_log").error(error_message)

                raise Exception("CamServer is not running on Pilatus server!")

        # Close fast and safety shutters
        logging.getLogger("user_level_log").info("Closing fast shutter")
        self.close_fast_shutter()

        # Now safety shutter
        self.close_safety_shutter()

        # reset collection id on each data collect
        self.collection_id = None

        # Preparing directory path for images and processing files
        # creating image file template and jpegs files templates
        file_parameters = data_collect_parameters["fileinfo"]

        file_parameters["suffix"] = self.bl_config.detector_fileext
        image_file_template = "%(prefix)s_%(run_number)s_%%04d.%(suffix)s" % file_parameters
        file_parameters["template"] = image_file_template

        archive_directory = self.get_archive_directory(file_parameters["directory"])
        data_collect_parameters["archive_dir"] = archive_directory

        if archive_directory:
            jpeg_filename="%s.jpeg" % os.path.splitext(image_file_template)[0]
            thumb_filename="%s.thumb.jpeg" % os.path.splitext(image_file_template)[0]
            jpeg_file_template = os.path.join(archive_directory, jpeg_filename)
            jpeg_thumbnail_file_template = os.path.join(archive_directory, thumb_filename)
        else:
            jpeg_file_template = None
            jpeg_thumbnail_file_template = None

        # database filling
        if self.bl_control.lims:
            data_collect_parameters["collection_start_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if self.bl_control.machine_current is not None:
                logging.getLogger("user_level_log").info("Getting synchrotron filling mode")
                data_collect_parameters["synchrotronMode"] = self.get_machine_fill_mode()
            data_collect_parameters["status"] = "failed"

            logging.getLogger("user_level_log").info("Storing data collection in LIMS")
            (self.collection_id, detector_id) = \
                                 self.bl_control.lims.store_data_collection(data_collect_parameters, self.bl_config)

            data_collect_parameters['collection_id'] = self.collection_id

            if detector_id:
                data_collect_parameters['detector_id'] = detector_id

        # Creating the directory for images and processing information
        logging.getLogger("user_level_log").info("Creating directory for images and processing")
        logging.getLogger('HWR').info("Directory: %s; File prefix: %s; Run number: %s" % (file_parameters["directory"], file_parameters["prefix"], str(file_parameters["run_number"])))

        self.create_directories(file_parameters['directory'],  file_parameters['process_directory'], file_parameters['log_directory'])
        self.xds_directory, self.mosflm_directory, self.hkl2000_directory = self.prepare_input_files(file_parameters["directory"], file_parameters["prefix"], file_parameters["run_number"], file_parameters['process_directory'])
        data_collect_parameters['xds_dir'] = self.xds_directory

        logging.getLogger("user_level_log").info("Getting sample info from parameters")
        sample_id, sample_location, sample_code = self.get_sample_info_from_parameters(data_collect_parameters)
        data_collect_parameters['blSampleId'] = sample_id

        if self.bl_control.sample_changer is not None:
            try:
                data_collect_parameters["actualSampleBarcode"] = \
                    self.bl_control.sample_changer.getLoadedSample().getID()
                data_collect_parameters["actualContainerBarcode"] = \
                    self.bl_control.sample_changer.getLoadedSample().getContainer().getID()

                logging.getLogger("user_level_log").info("Getting loaded sample coords")
                basket, vial = self.bl_control.sample_changer.getLoadedSample().getCoords()

                data_collect_parameters["actualSampleSlotInContainer"] = vial
                data_collect_parameters["actualContainerSlotInSC"] = basket
            except:
                data_collect_parameters["actualSampleBarcode"] = None
                data_collect_parameters["actualContainerBarcode"] = None
        else:
            data_collect_parameters["actualSampleBarcode"] = None
            data_collect_parameters["actualContainerBarcode"] = None

        centring_info = {}
        try:
            logging.getLogger("user_level_log").info("Getting centring status")
            centring_status = self.diffractometer().getCentringStatus()
        except:
            pass
        else:
            centring_info = dict(centring_status)

        #Save sample centring positions
        positions_str = ""
        motors = centring_info.get("motors", {}) #.update(centring_info.get("extraMotors", {}))
        motors_to_move_before_collect = data_collect_parameters.setdefault("motors", {})

        for motor, pos in motors.items():
              if motor in motors_to_move_before_collect:
                  continue
              motors_to_move_before_collect[motor]=pos

        current_diffractometer_position = self.diffractometer().getPositions()
        for motor in list(motors_to_move_before_collect.keys()):
            if motors_to_move_before_collect[motor] is None:
                del motors_to_move_before_collect[motor]
                try:
                    if current_diffractometer_position[motor] is not None:
                        positions_str += "%s=%f " % (motor, current_diffractometer_position[motor])
                except:
                    pass

        # this is for the LIMS
        positions_str += " ".join([motor+("=%f" % pos) for motor, pos in motors_to_move_before_collect.items()])
        data_collect_parameters['actualCenteringPosition'] = positions_str

        self.move_motors(motors_to_move_before_collect)
        # ------------------------------------------------------------------------
        # Start a process (in a new thread) to take care of snapshots...
        # ------------------------------------------------------------------------
        self._snapshot_camserver_number = 1

        # take snapshots, then assign centring status (which contains images) to centring_info variable
        logging.getLogger("user_level_log").info("Taking sample snapshots")
        self._take_crystal_snapshots(data_collect_parameters.get("take_snapshots", False))
        centring_info = self.bl_control.diffractometer.getCentringStatus()

        # move *again* motors, since taking snapshots may change positions
        logging.getLogger("user_level_log").info("Moving motors: %r", motors_to_move_before_collect)
        self.move_motors(motors_to_move_before_collect)

        if self.bl_control.lims:
          try:
            if self.current_lims_sample:
              self.current_lims_sample['lastKnownCentringPosition'] = positions_str
              logging.getLogger("user_level_log").info("Updating sample information in LIMS")
              self.bl_control.lims.update_bl_sample(self.current_lims_sample)
          except:
            logging.getLogger("HWR").exception("Could not update sample information in LIMS")

        # LNLS
        # Do not used by us....

        # if centring_info.get('images'):
        #   # Save snapshots
        #   snapshot_directory = self.get_archive_directory(file_parameters["directory"])

        #   try:
        #     logging.getLogger("user_level_log").info("Creating snapshosts directory: %r", snapshot_directory)
        #     self.create_directories(snapshot_directory)
        #   except:
        #       logging.getLogger("HWR").exception("Error creating snapshot directory")
        #   else:
        #       snapshot_i = 1
        #       snapshots = []
        #       for img in centring_info["images"]:
        #         img_phi_pos = img[0]
        #         img_data = img[1]
        #         snapshot_filename = "%s_%s_%s.snapshot.jpeg" % (file_parameters["prefix"],
        #                                                         file_parameters["run_number"],
        #                                                         snapshot_i)
        #         full_snapshot = os.path.join(snapshot_directory,
        #                                      snapshot_filename)

        #         try:
        #           f = open(full_snapshot, "w")
        #           logging.getLogger("user_level_log").info("Saving snapshot %d", snapshot_i)
        #           f.write(img_data)
        #         except:
        #           logging.getLogger("HWR").exception("Could not save snapshot!")
        #           try:
        #             f.close()
        #           except:
        #             pass

        #         data_collect_parameters['xtalSnapshotFullPath%i' % snapshot_i] = full_snapshot

        #         snapshots.append(full_snapshot)
        #         snapshot_i+=1

        #   try:
        #     data_collect_parameters["centeringMethod"] = centring_info['method']
        #   except:
        #     data_collect_parameters["centeringMethod"] = None

        if self.bl_control.lims:
            try:
                logging.getLogger("user_level_log").info("Updating data collection in LIMS")
                self.bl_control.lims.update_data_collection(data_collect_parameters)
            except:
                logging.getLogger("HWR").exception("Could not update data collection in LIMS")

        oscillation_parameters = data_collect_parameters["oscillation_sequence"][0]
        sample_id = data_collect_parameters['blSampleId']
        subwedge_size = oscillation_parameters.get("reference_interval", 1)

        #if data_collect_parameters["shutterless"]:
        #    subwedge_size = 1 
        #else:
        #    subwedge_size = oscillation_parameters["number_of_images"]
       
        wedges_to_collect = self.prepare_wedges_to_collect(oscillation_parameters["start"],
                                                           oscillation_parameters["number_of_images"],
                                                           oscillation_parameters["range"],
                                                           subwedge_size,
                                                           oscillation_parameters["overlap"])
        nframes = sum([wedge_size for _, wedge_size in wedges_to_collect])

        #Added exposure time for ProgressBarBrick. 
        #Extra time for each collection needs to be added (in this case 0.04)
        self.emit("collectNumberOfFrames", nframes, oscillation_parameters["exposure_time"] + 0.04)

        start_image_number = oscillation_parameters["start_image_number"]
        last_frame = start_image_number + nframes - 1
        if data_collect_parameters["skip_images"]:
            for start, wedge_size in wedges_to_collect[:]:
              filename = image_file_template % start_image_number
              file_location = file_parameters["directory"]
              file_path  = os.path.join(file_location, filename)
              if os.path.isfile(file_path):
                  logging.info("Skipping existing image %s", file_path)
                  del wedges_to_collect[0]
                  start_image_number += wedge_size
                  nframes -= wedge_size
              else:
                  # images have to be consecutive
                  break

        if nframes == 0:
            return

        if 'transmission' in data_collect_parameters:
            logging.getLogger("user_level_log").info("Setting transmission to %f", data_collect_parameters["transmission"])
            self.set_transmission(data_collect_parameters["transmission"])

        if 'wavelength' in data_collect_parameters:
            logging.getLogger("user_level_log").info("Setting wavelength to %f", data_collect_parameters["wavelength"])
            self.set_wavelength(data_collect_parameters["wavelength"])
        elif 'energy' in data_collect_parameters:
            logging.getLogger("user_level_log").info("Setting energy to %f", data_collect_parameters["energy"])
            self.set_energy(data_collect_parameters["energy"])

        # Wait unting energy and threshold are set...
        while ((not self.energy_hwobj.energyIsReady()) or (self.energy_hwobj.isSettingThreshold())):
            gevent.sleep(0.5)

        if 'resolution' in data_collect_parameters:
            resolution = data_collect_parameters["resolution"]["upper"]
            logging.getLogger("user_level_log").info("Setting resolution to %f", resolution)
            self.set_resolution(resolution)
        elif 'detdistance' in oscillation_parameters:
            logging.getLogger("user_level_log").info("Moving detector to %f", data_collect_parameters["detdistance"])
            self.move_detector(oscillation_parameters["detdistance"])

        # ----------------------------------------------------------------------------------------------
        # Data collection
        # ---------------
        # Set main detector info (which will be stored in .CBF);
        # Set omega velocity for experiment;
        # Set detector to acquire state;
        # ----------------------------------------------------------------------------------------------
        self.data_collection_hook(data_collect_parameters)

        # 0:software binned, 1:unbinned, 2:hw binned
        self.set_detector_mode(data_collect_parameters["detector_mode"])

        # Using data-collection
        with cleanup(self.data_collection_cleanup):
            # Control of shutter
            if not self.safety_shutter_opened():
                logging.getLogger("user_level_log").info("Opening safety shutter")
                # ------------------------------------------------------------------
                # LNLS
                # ------------------------------------------------------------------
                # Start trigger by openning the shutter and start another thread 
                # to take care of shutter clossing and Pilatus IOC to prepare for receive trigger...
                # ------------------------------------------------------------------
                self._shutter_control_gen = gevent.spawn(self.do_shutter_control)
                # ------------------------------------------------------------------
                self.open_safety_shutter(moveOmega=self._total_angle)

            logging.getLogger("user_level_log").info("Preparing intensity monitors")
            self.prepare_intensity_monitors()

            frame = start_image_number
            osc_range = oscillation_parameters["range"]
            exptime = oscillation_parameters["exposure_time"]
            npass = oscillation_parameters["number_of_passes"]

            # update LIMS
            if self.bl_control.lims:
                try:
                    logging.getLogger("user_level_log").info("Gathering data for LIMS update")
                    data_collect_parameters["flux"] = self.get_flux()
                    data_collect_parameters["flux_end"] = data_collect_parameters["flux"]
                    data_collect_parameters["wavelength"]= self.get_wavelength()
                    data_collect_parameters["detectorDistance"] =  self.get_detector_distance()
                    data_collect_parameters["resolution"] = self.get_resolution()
                    data_collect_parameters["transmission"] = self.get_transmission()
                    beam_centre_x, beam_centre_y = self.get_beam_centre()
                    data_collect_parameters["xBeam"] = beam_centre_x
                    data_collect_parameters["yBeam"] = beam_centre_y

                    und = self.get_undulators_gaps()
                    i = 1
                    for jj in self.bl_config.undulators:
                        key = jj.type
                        if key in und:
                            data_collect_parameters["undulatorGap%d" % (i)] = und[key]
                            i += 1
                    data_collect_parameters["resolutionAtCorner"] = self.get_resolution_at_corner()
                    beam_size_x, beam_size_y = self.get_beam_size()
                    data_collect_parameters["beamSizeAtSampleX"] = beam_size_x
                    data_collect_parameters["beamSizeAtSampleY"] = beam_size_y
                    data_collect_parameters["beamShape"] = self.get_beam_shape()
                    hor_gap, vert_gap = self.get_slit_gaps()
                    data_collect_parameters["slitGapHorizontal"] = hor_gap
                    data_collect_parameters["slitGapVertical"] = vert_gap

                    logging.getLogger("user_level_log").info("Updating data collection in LIMS")
                    self.bl_control.lims.update_data_collection(data_collect_parameters, wait=True)
                    logging.getLogger("user_level_log").info("Done updating data collection in LIMS")
                except:
                    logging.getLogger("HWR").exception("Could not store data collection into LIMS")

            if self.bl_control.lims and self.bl_config.input_files_server:
                logging.getLogger("user_level_log").info("Asking for input files writing")
                self.write_input_files(self.collection_id, wait=False) 

            # at this point input files should have been written           
            # TODO aggree what parameters will be sent to this function
            if data_collect_parameters.get("processing", False)=="True":
                self.trigger_auto_processing("before",
                                       self.xds_directory,
                                       data_collect_parameters["EDNA_files_dir"],
                                       data_collect_parameters["anomalous"],
                                       data_collect_parameters["residues"],
                                       data_collect_parameters["do_inducedraddam"],
                                       data_collect_parameters.get("sample_reference", {}).get("spacegroup", ""),
                                       data_collect_parameters.get("sample_reference", {}).get("cell", ""))
            if self.run_without_loop:
                self.execute_collect_without_loop(data_collect_parameters)
            else: 
                for start, wedge_size in wedges_to_collect:
                    logging.getLogger("user_level_log").info("Preparing acquisition, start=%f, wedge size=%d", start, wedge_size)
                    self.prepare_acquisition(1 if data_collect_parameters.get("dark", 0) else 0,
                                             start,
                                             osc_range,
                                             exptime,
                                             npass,
                                             wedge_size,
                                             data_collect_parameters["comment"])
                    data_collect_parameters["dark"] = 0

                    i = 0
                    j = wedge_size

                    #while ((j > 0) and self._shutter_control_gen):
                    #logging.getLogger("HWR").exception("BEFORE self._shutter_control_gen: %s" % str(self._shutter_control_gen))
                    while (j > 0):
                      frame_start = start+i*osc_range
                      i+=1

                      filename = image_file_template % frame
                      try:
                        jpeg_full_path = jpeg_file_template % frame
                        jpeg_thumbnail_full_path = jpeg_thumbnail_file_template % frame
                      except:
                        jpeg_full_path = None
                        jpeg_thumbnail_full_path = None
                      file_location = file_parameters["directory"]
                      file_path  = os.path.join(file_location, filename)

                      self.set_detector_filenames(frame, frame_start, str(file_path), str(jpeg_full_path), str(jpeg_thumbnail_full_path))
                      osc_start, osc_end = self.prepare_oscillation(frame_start, osc_range, exptime, npass)

                      with error_cleanup(self.reset_detector):
                          self.do_oscillation(start=osc_start, end=osc_end, exptime=exptime, npass=npass)
                          self.write_image(j == 1)
                                     
                          # Store image in lims
                          if self.bl_control.lims:
                            if self.store_image_in_lims(frame, j == wedge_size, j == 1):
                              lims_image={'dataCollectionId': self.collection_id,
                                          'fileName': filename,
                                          'fileLocation': file_location,
                                          'imageNumber': frame,
                                          'measuredIntensity': self.get_measured_intensity(),
                                          'synchrotronCurrent': self.get_machine_current(),
                                          'machineMessage': self.get_machine_message(),
                                          'temperature': self.get_cryo_temperature()}

                              if archive_directory:
                                lims_image['jpegFileFullPath'] = jpeg_full_path
                                lims_image['jpegThumbnailFileFullPath'] = jpeg_thumbnail_full_path

                              try:
                                  self.bl_control.lims.store_image(lims_image)
                              except:
                                  logging.getLogger("HWR").exception("Could not store image in LIMS")
                          
                              self.generate_image_jpeg(str(file_path), str(jpeg_full_path), str(jpeg_thumbnail_full_path),wait=False)
                          if data_collect_parameters.get("processing", False)=="True":
                            self.trigger_auto_processing("image",
                                                         self.xds_directory,
                                                         data_collect_parameters["EDNA_files_dir"],
                                                         data_collect_parameters["anomalous"],
                                                         data_collect_parameters["residues"],
                                                         data_collect_parameters["do_inducedraddam"],
                                                         data_collect_parameters.get("sample_reference", {}).get("spacegroup", ""),
                                                         data_collect_parameters.get("sample_reference", {}).get("cell", ""),
                                                         frame,
                                                         data_collect_parameters['oscillation_sequence'][0]['number_of_images'])

                          if data_collect_parameters.get("shutterless"):
                              with gevent.Timeout(10, RuntimeError("Timeout waiting for detector trigger, no image taken")):
                                  while self.last_image_saved() == 0:
                                      time.sleep(exptime)
                          
                              last_image_saved = self.last_image_saved()
                              if last_image_saved < wedge_size:
                                  time.sleep(exptime*wedge_size/100.0)
                                  last_image_saved = self.last_image_saved()
                              frame = max(start_image_number+1, start_image_number+last_image_saved-1)
                              self.emit("collectImageTaken", frame)
                              j = wedge_size - last_image_saved
                          else:
                              j -= 1
                              self.emit("collectImageTaken", frame)
                              frame += 1
                              if j == 0:
                                break

    @task
    def loop(self, owner, data_collect_parameters_list):
        failed_msg = "Data collection failed!"
        failed = True
        collections_analyse_params = []

        try:
            self.emit("collectReady", (False, ))
            self.emit("collectStarted", (owner, 1))

            for data_collect_parameters in data_collect_parameters_list:
                logging.debug("%s - collect parameters = %r" % (self.__class__.__name__, data_collect_parameters))

                # Store file directory to be used by local auto_processing
                self._file_directory = data_collect_parameters["fileinfo"]["directory"]
                self._snapshot_directory = data_collect_parameters["fileinfo"]["snapshot_directory"]
                self._log_directory = data_collect_parameters["fileinfo"]["log_directory"]
                self._file_prefix = data_collect_parameters["fileinfo"]["prefix"]
                self._file_run_number = data_collect_parameters["fileinfo"]["run_number"]

                # Store initial and final angle to be used by snapshot
                self._initial_angle = data_collect_parameters['oscillation_sequence'][0]['start']
                numImages = float(data_collect_parameters['oscillation_sequence'][0]['number_of_images'])
                angleIncr = float(data_collect_parameters['oscillation_sequence'][0]['range'])
                self._total_angle   = self._initial_angle + (angleIncr * numImages)

                # Initialize failed with False
                failed = False

                try:
                    # emit signals to make bricks happy
                    osc_id, sample_id, sample_code, sample_location = self.update_oscillations_history(data_collect_parameters)
                    self.emit('collectOscillationStarted', (owner, sample_id, sample_code, sample_location, data_collect_parameters, osc_id))
                    data_collect_parameters["status"]='Running'

                    # Store previous Omega velocity
                    self._previous_omega_velo = self.diffractometer_hwobj.get_omega_velocity()                    

                    # Move goniometer to initial angle position
                    self.diffractometer_hwobj.move_omega_initial_angle(data_collect_parameters['oscillation_sequence'][0]['start'])

                    # now really start collect sequence
                    self.do_collect(owner, data_collect_parameters)
                except:
                    failed = True
                    exc_type, exc_value, exc_tb = sys.exc_info()
                    logging.exception("Data collection failed")
                    data_collect_parameters["status"] = 'Data collection failed!' #Message to be stored in LIMS
                    failed_msg = 'Data collection failed!\n%s' % exc_value
                    self.emit("collectOscillationFailed", (owner, False, failed_msg, self.collection_id, osc_id))
                else:
                    data_collect_parameters["status"]='Data collection successful'

                try:
                    if data_collect_parameters.get("processing", False)=="True":
                        self.trigger_auto_processing("after",
                                                 self.xds_directory,
                                                 data_collect_parameters["EDNA_files_dir"],
                                                 data_collect_parameters["anomalous"],
                                                 data_collect_parameters["residues"],
                                                 data_collect_parameters["do_inducedraddam"],
                                                 data_collect_parameters.get("sample_reference", {}).get("spacegroup", ""),
                                                 data_collect_parameters.get("sample_reference", {}).get("cell", ""),
                                                 data_collect_parameters['oscillation_sequence'][0]['number_of_images'])
                except:
                    pass
                else:
                    collections_analyse_params.append((self.collection_id,
                                                      self.xds_directory, 
                                                      data_collect_parameters["EDNA_files_dir"],
                                                      data_collect_parameters["anomalous"],
                                                      data_collect_parameters["residues"],
                                                      "reference_interval" in data_collect_parameters["oscillation_sequence"][0],
                                                      data_collect_parameters["do_inducedraddam"]))

                if self.bl_control.lims:
                    data_collect_parameters["flux_end"]=self.get_flux()
                    try:
                        self.bl_control.lims.update_data_collection(data_collect_parameters)
                    except:
                        logging.getLogger("HWR").exception("Could not store data collection into LIMS")

                if failed:
                    # if one dc fails, stop the whole loop
                    break
                else:
                    self.emit("collectOscillationFinished", (owner, True, data_collect_parameters["status"], self.collection_id, osc_id, data_collect_parameters))

                    # If exist a thread to take care of shutter, kill it
                    self.stop_shutter_control()

                    # Wait a while to guarantee all files can be copied
                    gevent.sleep(5)

                    # Cleanup of temporary folder
                    if (self.detector_hwobj.get_pilatus_server_storage() in self._file_directory):
                        self.detector_hwobj.cleanup_remote_folder(os.path.join(self.detector_hwobj.get_pilatus_server_storage_temp(), os.getenv("USER")))
                    else:
                        # it is not saved in '/storage', but some other local place, like '/home/ABTLUS/douglas.beniz/Documents'
                        folder = self._file_directory[1:self._file_directory[1:].find('/')+1]
                        if (folder == ''):
                            folder = "*.cbf"

                        self.detector_hwobj.cleanup_remote_folder(os.path.join(self.detector_hwobj.get_pilatus_server_storage_temp(), folder))
        except:
            logging.getLogger('HWR').info("Killed!")
        finally:
            self.emit("collectEnded", owner, not failed, failed_msg if failed else "Data collection successful")
            logging.getLogger('HWR').info("data collection successful in loop")
            self.emit("collectReady", (True, ))

    @task
    def take_crystal_snapshots(self, number_of_snapshots):
        # Parameters read from user interface
        fileName = str(self._file_prefix) + "_" + str(self._file_run_number)

        # Parameters of temporary file generation
        logDirectory = self._log_directory.replace(self.detector_hwobj.get_pilatus_server_storage(), self.detector_hwobj.get_pilatus_server_storage_temp())

        # Call snapshot procedure from Camera hardware object
        try:
            self.camera_hwobj.take_snapshots(image_count=number_of_snapshots, snapshotFilePath=self._snapshot_directory, snapshotFilePrefix=fileName, logFilePath=logDirectory, runNumber=self._file_run_number, collectStart=self._initial_angle, collectEnd=self._total_angle, motorHwobj=self.motor_omega_hwobj, detectorHwobj=self.detector_hwobj)
        except:
            logging.getLogger("HWR").error("LNLSMultiCollect: Problem to take snapshots!")

    @task
    def data_collection_hook(self, data_collect_parameters):
        """
        Descript. : 
        """
        p = data_collect_parameters

        # Parameters read from user interface
        if (self.detector_hwobj.get_pilatus_server_storage() in str(p["fileinfo"]["directory"])):
            filePath = str(p["fileinfo"]["directory"]) + "\0"
            filePath = filePath.replace(self.detector_hwobj.get_pilatus_server_storage(), self.detector_hwobj.get_pilatus_server_storage_temp())
        else:
            filePath = os.path.join(self.detector_hwobj.get_pilatus_server_storage_temp(), str(p["fileinfo"]["directory"])[1:])

        fileName = str(p["fileinfo"]["prefix"]) + "_" + str(p["fileinfo"]["run_number"]) + "_" + str(p["oscillation_sequence"][0]["start_image_number"]).zfill(5) + "." + str(self.fileSuffix()) + "\0"
        #fileTemplate = str(p['fileinfo']['template']) + "\0"
        # e.g.: test9_mx1_1_%04d.cbf
        fileTemplate = str("%s%s." + self.fileSuffix() + "\0")
        acquireTime = p['oscillation_sequence'][0]['exposure_time']
        numImages   = p['oscillation_sequence'][0]['number_of_images']
        startAngle  = p['oscillation_sequence'][0]['start']
        self._initial_angle = startAngle
        angleIncr   = p['oscillation_sequence'][0]['range']

        shutterless = p['shutterless']
        if (shutterless):
            triggerMode = self.detector_hwobj.TRIGGER_MODE["Internal"]
        else:
            triggerMode = self.detector_hwobj.TRIGGER_MODE["Ext. Trigger"]

        # Calculated parameters
        self._total_angle   = (angleIncr * numImages)
        self._total_time    = (acquireTime * numImages)
        self._total_time_readout = ((acquireTime + self.detector_hwobj.get_readout_per_image()) * numImages)
        #oscilationVelo      = (self._total_angle / self._total_time)           # degrees per second (without readout)
        oscilationVelo      = (self._total_angle / self._total_time_readout)     # degrees per second (with readout)
        oscilationVeloRPM   = (oscilationVelo * 60 / 360)
        # Total angle absolute, including the inicial angle (already moved)
        self._total_angle   += startAngle

        # Setting the configuration in Pilatus (to fill in header of images)
        self.detector_hwobj.set_file_path(filePath)
        self.detector_hwobj.set_file_name(fileName)
        self.detector_hwobj.set_file_template(fileTemplate)
        self.detector_hwobj.set_acquire_time(acquireTime)
        self.detector_hwobj.set_acquire_period(acquireTime + 0.0023)  # periodic time
        self.detector_hwobj.set_delay_time(0.0)
        self.detector_hwobj.set_num_images(numImages)
        self.detector_hwobj.set_start_angle(startAngle)
        self.detector_hwobj.set_angle_incr(angleIncr)
        self.detector_hwobj.set_det_dist(self.get_detector_distance())
        self.detector_hwobj.set_det_2_theta(0.0)
        self.detector_hwobj.set_wavelength(self.get_wavelength())
        self.detector_hwobj.set_beam_position(list(self.get_beam_centre()))
        self.detector_hwobj.set_trigger_mode(triggerMode)

        # Set Omega velocity (RPM) for acquisition
        self.diffractometer_hwobj.set_omega_velocity(oscilationVeloRPM)

        return

    def do_prepare_oscillation(self, start, end, exptime, npass):
        self.actual_frame_num = 0
    
    @task
    def oscil(self, start, end, exptime, npass):
        return

    @task
    def set_transmission(self, transmission_percent):
        return

    def set_wavelength(self, wavelength):
        logging.debug("%s - set_wavelength: %f" % (self.__class__.__name__, wavelength))
        self.energy_hwobj.setWavelength(wavelength)

    def set_energy(self, energy):
        logging.debug("%s - set_energy: %f" % (self.__class__.__name__, energy))
        self.energy_hwobj.setEnergy(energy)

    @task
    def set_resolution(self, new_resolution):
        logging.debug("%s - set_resolution: %f" % (self.__class__.__name__, new_resolution))

        # Move detector distance to achieve such resolution
        self.resolution_hwobj.move(res=new_resolution, wait=True)

    @task
    def move_detector(self, detector_distance):
        logging.debug("%s - move_detector: %f" % (self.__class__.__name__, detector_distance))
        return

    @task
    def data_collection_cleanup(self):
        return 

    @task
    def close_fast_shutter(self):
        return

    @task
    def open_fast_shutter(self):
        return

    @task
    def move_motors(self, motor_position_dict):
        return

    @task
    def open_safety_shutter(self, moveOmega=None):
        logging.getLogger("user_level_log").info("Openning shutter: %s" %  time.strftime("%d/%m/%Y %H:%M:%S"))

        # Open detector shutter
        self.detector_hwobj.open_shutter()

        # Disable UI controls to operate shutter
        if (self.shutter_hwobj):
            self.shutter_hwobj.enableControls(enable=False)

        if (moveOmega):
            # Send a comand to move omega
            self.diffractometer_hwobj.move_omega_absolute(moveOmega)


    def safety_shutter_opened(self):
        return self.detector_hwobj.shutter_opened()


    @task
    def close_safety_shutter(self, restoreOmegaPosition=False):
        # gevent.sleep(0.2)

        # shutterClosed = False
        # tries = 0

        # while (not shutterClosed and tries < MAXIMUM_TRIES_CLOSE_SHUTTER):
        if (self.safety_shutter_opened() or (self.diffractometer_hwobj.get_omega_position() != self._initial_angle and not self.diffractometer_hwobj.is_omega_moving())):
            logging.getLogger("user_level_log").info("Closing safety shutter at: %s" %  time.strftime("%d/%m/%Y %H:%M:%S"))

            try:
                # Close detector shutter
                if self.detector_hwobj:
                    self.detector_hwobj.close_shutter()
                    # shutterClosed = True

                # Enable UI controls to operate shutter
                if (self.shutter_hwobj):
                    self.shutter_hwobj.enableControls()

                if (restoreOmegaPosition):
                    # Restore omega motor velocity
                    #self.diffractometer_hwobj.set_omega_velocity(self._previous_omega_velo)    # OBSOLETE
                    self.diffractometer_hwobj.set_omega_default_velocity()

                    # Send a comand to move omega back to its initial position
                    self.diffractometer_hwobj.move_omega_absolute(self._initial_angle)
            except:
                logging.getLogger("HWR").exception("Could not close safety shutter!")
                logging.getLogger("user_level_log").error("Could not close safety shutter!")
            # else:
            #     print("Still not closed....")

            # tries += 1


    @task
    def prepare_intensity_monitors(self):
        return

    def prepare_acquisition(self, take_dark, start, osc_range, exptime, npass, number_of_images, comment=""):
        return

    def set_detector_filenames(self, frame_number, start, filename, jpeg_full_path, jpeg_thumbnail_full_path):
        return

    def prepare_oscillation(self, start, osc_range, exptime, npass):
        return (start, start+osc_range)
    
    def do_oscillation(self, start, end, exptime, npass):
        gevent.sleep(exptime)
  
    def start_acquisition(self, exptime, npass, first_frame):
        # Check if Pilatus is not still collecting...
        if (self.detector_hwobj.is_counting()):
            logging.getLogger("user_level_log").info("Area detector of Pilatus inform that it is still in operation.  Waiting at most 1 minute...")

        tries = 0
        while(self.detector_hwobj.is_counting() and tries < MAXIMUM_TRIES_AD_PILATUS):
            gevent.sleep(0.5)
            tries += 1

        # If still "acquiring"... Try to stop previous pilatus (CamServer) acquisition
        if (self.detector_hwobj.is_counting()):
            logging.getLogger("user_level_log").info("Forcing previous Pilatus acquisition to stop...")
            self.force_pilatus_stop()

        # Send command to start acquisition (wait trigger)
        self.detector_hwobj.acquire()

        # Reset thread object that take care of stop procedure
        self._stop_procedure_gen = None

        return


    def do_shutter_control(self):
        print("start stop_shutter_control")
        self.start_acquisition(exptime=None, npass=None, first_frame=None)
        print("self._total_time_readout: ", self._total_time_readout)
        self.do_oscillation(start=None, end=None, exptime=self._total_time_readout, npass=None)
        print("calling stop_acquisition")
        self.stop_acquisition()


    def stop_acquisition(self):
        # Close shutter and move Omega to initial position
        self.close_safety_shutter(restoreOmegaPosition=True)

        return


    def write_image(self, last_frame):
        self.actual_frame_num += 1
        return


    def last_image_saved(self):
        return self.actual_frame_num


    def stop_shutter_control(self):
        # If exist a thread to take care of shutter, kill it
        if (self._shutter_control_gen):
            self._shutter_control_gen.kill()
            self._shutter_control_gen = None

        return


    def force_pilatus_stop(self):
        # Try to stop pilatus (CamServer)
        try:
            # XXX
            # Just for guarantee... this should be investigated!
            self.detector_hwobj.stop()
            gevent.sleep(2)
            self.detector_hwobj.acquire()
            gevent.sleep(2)
            self.detector_hwobj.stop()
            gevent.sleep(2)
        except:
            logging.getLogger("user_level_log").error("Error when trying to stop Pilatus acquisition...")
            pass


    def stop_procedure(self):
        # If exist a thread to take care of shutter, kill it
        self.stop_shutter_control()

        # Close shutter and move Omega to initial position
        self.close_safety_shutter(restoreOmegaPosition=True)

        # Try to stop pilatus (CamServer)
        self.force_pilatus_stop()

        try:
            # Cancel snapshots
            if self.camera_hwobj is not None:
                self.camera_hwobj.cancel_snapshot()
        except:
            logging.getLogger("user_level_log").error("Error when trying to stop Snapshots process...")
            pass

        # Wait a while to guarantee all files can be copied
        gevent.sleep(5)

        try:
            # Cleanup of temporary folder
            if (self.detector_hwobj.get_pilatus_server_storage() in self._file_directory):
                self.detector_hwobj.cleanup_remote_folder(os.path.join(self.detector_hwobj.get_pilatus_server_storage_temp(), os.getenv("USER")))
            else:
                # it is not saved in '/storage', but some other local place, like '/home/ABTLUS/douglas.beniz/Documents'
                folder = self._file_directory[1:self._file_directory[1:].find('/')+1]
                if (folder == ''):
                    folder = "*.cbf"

                self.detector_hwobj.cleanup_remote_folder(os.path.join(self.detector_hwobj.get_pilatus_server_storage_temp(), folder))
        except:
            logging.getLogger("user_level_log").error("Error when trying to cleanup Pilatus temporary folder...")
            pass


    def stopCollect(self, owner):
        if (not self._stop_procedure_gen):
            logging.getLogger("user_level_log").error("User recquired the end of collection!")

            # Open a thread to take care of ending processing            
            self._stop_procedure_gen = gevent.spawn(self.stop_procedure)

            # Calling parent method
            logging.debug("%s - calling AbstractMultiCollect.stopCollect()" % (self.__class__.__name__))
            AbstractMultiCollect.stopCollect(self, owner)


    def reset_detector(self):
        return


    def prepare_input_files(self, files_directory, prefix, run_number, process_directory):
        self.actual_frame_num = 0
        i = 1
        while True:
          xds_input_file_dirname = "xds_%s_run%s_%d" % (prefix, run_number, i)
          xds_directory = os.path.join(process_directory, xds_input_file_dirname)

          if not os.path.exists(xds_directory):
            break

          i+=1

        mosflm_input_file_dirname = "mosflm_%s_run%s_%d" % (prefix, run_number, i)
        mosflm_directory = os.path.join(process_directory, mosflm_input_file_dirname)

        hkl2000_dirname = "hkl2000_%s_run%s_%d" % (prefix, run_number, i)
        hkl2000_directory = os.path.join(process_directory, hkl2000_dirname)

        self.raw_data_input_file_dir = os.path.join(files_directory, "process", xds_input_file_dirname)
        self.mosflm_raw_data_input_file_dir = os.path.join(files_directory, "process", mosflm_input_file_dirname)
        self.raw_hkl2000_dir = os.path.join(files_directory, "process", hkl2000_dirname)

        return xds_directory, mosflm_directory, hkl2000_directory


    @task
    def write_input_files(self, collection_id):
        return

    def get_wavelength(self):
        if self.energy_hwobj is not None:
            return self.energy_hwobj.getCurrentWavelength()

    def get_detector_distance(self):
        if self.detector_hwobj is not None:
            return self.detector_hwobj.get_distance()
       
    def get_resolution(self):
        if self.bl_control.resolution is not None:
            return self.bl_control.resolution.getPosition()

    def get_transmission(self):
        if self.bl_control.transmission is not None:
            return self.bl_control.transmission.getAttFactor()

    def get_undulators_gaps(self):
        return []

    def get_resolution_at_corner(self):
        return

    def get_beam_size(self):
        return None, None

    def get_slit_gaps(self):
        return None, None

    def get_beam_shape(self):
        return
    
    def get_measured_intensity(self):
        return

    def get_machine_current(self):
        if self.bl_control.machine_current is not None:
            return self.bl_control.machine_current.getCurrent()
        else:
            return 0

    def get_machine_message(self):
        if  self.bl_control.machine_current is not None:
            return self.bl_control.machine_current.getMessage()
        else:
            return ''

    def get_machine_fill_mode(self):
        if self.bl_control.machine_current is not None:
            return self.bl_control.machine_current.getFillMode()
        else:
            ''
    def get_cryo_temperature(self):
        if self.bl_control.cryo_stream is not None: 
            return self.bl_control.cryo_stream.getTemperature()

    def getCurrentEnergy(self):
        return

    def get_beam_centre(self):
        if self.beam_info_hwobj is not None:
            #return self.beam_info_hwobj.get_beam_position()
            return self.beam_info_hwobj.get_beam_det_position()
        else:
            return None, None

    def getBeamlineConfiguration(self, *args):
        return self.bl_config._asdict()

    def isConnected(self):
        return True

    def isReady(self):
        return True
 
    def sampleChangerHO(self):
        return self.bl_control.sample_changer

    def diffractometer(self):
        return self.bl_control.diffractometer

    def sanityCheck(self, collect_params):
        return
    
    def setBrick(self, brick):
        return

    def directoryPrefix(self):
        return self.bl_config.directory_prefix

    def fileSuffix(self):
        return self.bl_config.detector_fileext

    def store_image_in_lims(self, frame, first_frame, last_frame):
        return True

    def get_flux(self):
        if self.bl_control.flux is not None:
            return self.bl_control.flux.getCurrentFlux()

    def getOscillation(self, oscillation_id):
        return self.oscillations_history[oscillation_id - 1]
       
    def sampleAcceptCentring(self, accepted, centring_status):
        self.sample_centring_done(accepted, centring_status)

    def setCentringStatus(self, centring_status):
        self._centring_status = centring_status

    def getOscillations(self,session_id):
        return []

    def set_helical(self, helical_on):
        return

    def set_helical_pos(self, helical_oscil_pos):
        return

    def get_archive_directory(self, directory):
        archive_dir = os.path.join(directory, 'archive')
        return archive_dir

    @task
    def generate_image_jpeg(self, filename, jpeg_path, jpeg_thumbnail_path):
        pass


    def nextCamserverScreenshotFileNumber(self, name):
        leadingZeros = 4

        fileName, fileExtension = os.path.splitext(name)
        filePath, fileName = os.path.split(fileName)

        # check if fileName contains the number part and if so ignores it to
        # generate the next part
        expression = r'_\d{'+str(leadingZeros)+'}'
        fileName = re.sub(expression,'', fileName, count=1)
        fileName = os.path.join(filePath, fileName)

        newName = ""
        cont = 0

        while(True):
            cont += 1
            newName = fileName + "_" + str(cont).zfill(leadingZeros) + fileExtension

            if(os.path.isfile(newName)):
                continue
            else:
                break

        return cont


    """
    processDataScripts
        Description    : executes a script after the data collection has finished
        Type           : method
    """
    def trigger_auto_processing(self, process_event, xds_dir, EDNA_files_dir=None, anomalous=None, residues=200, do_inducedraddam=False, spacegroup=None, cell=None, frame=None, number_of_images=None):
        cbfFileName = None
        pngFileName = None

        #if (process_event == "image" and self._shutter_control_gen):
        #logging.getLogger("HWR").exception("AFTER self._shutter_control_gen: %s" % str(self._shutter_control_gen))
        if (process_event == "image"):
            # -----------------------------------------------------------------
            # Perform the copy of CBF file from temporary to definite place in storage
            # -----------------------------------------------------------------
            try:
                if (frame):
                    filePathDest = self._file_directory

                    if (self.detector_hwobj.get_pilatus_server_storage() in filePathDest):
                        filePathOrig = filePathDest.replace(self.detector_hwobj.get_pilatus_server_storage(), self.detector_hwobj.get_pilatus_server_storage_temp())
                    else:
                        filePathOrig = os.path.join(self.detector_hwobj.get_pilatus_server_storage_temp(), filePathDest[1:])

                    copied = False
                    copyingLogFile = False
                    tries = 0

                    cbfFileCriteria =  str(self._file_prefix) + "_"
                    cbfFileCriteria += str(self._file_run_number) + "_"
                    #cbfFileCriteria += str(self._file_run_number) + "*"
                    #if (number_of_images and (number_of_images > 1)):
                    #    cbfFileCriteria += str(frame).zfill(5)
                    cbfFileCriteria += str(frame).zfill(5)
                    cbfFileCriteria += "."
                    cbfFileCriteria += str(self.fileSuffix())

                    user = os.getenv("USER")

                    while ((not copied) and (tries < MAXIMUM_TRIES_COPY_CBF)):
                        for cbfFile in glob.glob(os.path.join(filePathOrig, cbfFileCriteria)):
                            # To use if error
                            cbfFileName = cbfFile
                            # This was to try perform a fast CBF transference
                            #self.detector_hwobj.change_file_owner(cbfFile, user)
                            
                            # -------------------------------------------
                            # Running OK
                            ###cbfFileName = os.path.join(filePathOrig, cbfFileCriteria)
                            ###copied = self.detector_hwobj.change_file_owner_and_move(fullFileNameOrig=cbfFileName, fullPathDest=filePathDest, owner=user)
                            # -------------------------------------------

                            shutil.copy(cbfFile, filePathDest)

                            #try:
                            #    shutil.move(cbfFile, filePathDest)
                            #except:
                            #    pass
                            #rsync(cbfFile, filePathDest)

                            copied = True

                            # If it is the last image to copy, also wait for LOG file
                            if ((not copyingLogFile) and (number_of_images > 1) and (frame == number_of_images)):
                                cbfFileCriteria =  str(self._file_prefix) + "_" 
                                cbfFileCriteria += str(self._file_run_number) + "*.log"

                                copyingLogFile = True

                                copied = False
                                tries = 0

                            # -----------------------------------------------------------------
                            # Perform the copy of PNG images of CamServer execution from temporary to definite place in storage
                            # -----------------------------------------------------------------
                            try:
                                if (frame):
                                    filePathDestLog = self._log_directory

                                    if (self.detector_hwobj.get_pilatus_server_storage() in filePathDestLog):
                                        filePathOrigLog = filePathDestLog.replace(self.detector_hwobj.get_pilatus_server_storage(), self.detector_hwobj.get_pilatus_server_storage_temp())
                                    else:
                                        filePathOrigLog = os.path.join(self.detector_hwobj.get_pilatus_server_storage_temp(), filePathDestLog[1:])

                                    pngFileCriteria =  str(self.detector_hwobj.get_camserver_screenshot_name()) + "_"
                                    pngFileCriteria += str(self._file_run_number) + "_"
                                    pngFileCriteria += str(self._snapshot_camserver_number).zfill(4)
                                    pngFileCriteria += ".png"

                                    for pngFile in glob.glob(os.path.join(filePathOrigLog, pngFileCriteria)):
                                        # To use if error
                                        pngFileName = pngFile
                                        # 
                                        shutil.copy(pngFile, filePathDestLog)
                                        #rsync(pngFile, filePathDestLog)
                                        #copied = True
                                        self._snapshot_camserver_number += 1

                            except:
                                logging.getLogger("HWR").exception("Error when copying PNG files from CamServer: %s" % pngFileName)
                                logging.getLogger("user_level_log").error("Error when copying PNG files from CamServer: %s" % pngFileName)

                        if (not copied):
                            tries += 1
                            # A short sleep to be sure the files will be there
                            gevent.sleep(0.01)

            except:
                logging.getLogger("HWR").exception("Error when copying CBF files: %s" % cbfFileName)
                logging.getLogger("user_level_log").error("Error when copying CBF files: %s" % cbfFileName)

            if (cbfFileName is None):
                logging.getLogger("HWR").exception("No CBF file copied! Check Storage and Pilatus...")
                logging.getLogger("user_level_log").error("No CBF file copied! Check Storage and Pilatus...")
            else:
                # Success copying CBF file... inform interface to allow navigation (view) of it (them)
                self.emit("collectHasCbfToView", True)

        # Call parent method
        AbstractMultiCollect.trigger_auto_processing(self, process_event, xds_dir, EDNA_files_dir, anomalous, residues, do_inducedraddam, spacegroup, cell, frame)
