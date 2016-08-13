from HardwareRepository.BaseHardwareObjects import HardwareObject
from AbstractMultiCollect import *
import logging
import time
import os
import http.client
import math
import gevent
import glob
import shutil


MAXIMUM_TRIES_COPY_CBF = 50

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
        self._previous_omega_velo = None
        self._total_angle = None
        self._total_time = None
        self._total_time_redout = None
        self._initial_angle = None
        self._file_directory = None
        self._file_prefix = None
        self._file_run_number = None

        self.diffractometer_hwobj = self.getObjectByRole("diffractometer")
        self.lims_client_hwobj = self.getObjectByRole("lims_client")
        self.machine_current_hwobj = self.getObjectByRole("machine_current")
        self.energy_hwobj = self.getObjectByRole("energy")
        self.resolution_hwobj = self.getObjectByRole("resolution")
        self.transmission_hwobj = self.getObjectByRole("transmission")
        self.detector_hwobj = self.getObjectByRole("detector")
        self.beam_info_hwobj = self.getObjectByRole("beam_info")
        self.autoprocessing_hwobj = self.getObjectByRole("auto_processing")

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

    @task
    def loop(self, owner, data_collect_parameters_list):
        failed_msg = "Data collection failed!"
        failed = True
        collections_analyse_params = []

        try:
            self.emit("collectReady", (False, ))
            self.emit("collectStarted", (owner, 1))
            print("**************************************************************************************************")
            print("LNLSMultiCollect - collectStarted")
            for data_collect_parameters in data_collect_parameters_list:
                logging.debug("collect parameters = %r", data_collect_parameters)
                print("*******************************************************************************************")
                print("LNLSMultiCollect - collect parameters = %r" % data_collect_parameters)
                print("*******************************************************************************************")

                # Store file directory to be used by local auto_processing
                self._file_directory = data_collect_parameters["fileinfo"]["directory"]
                self._file_prefix = data_collect_parameters["fileinfo"]["prefix"]
                self._file_run_number = data_collect_parameters["fileinfo"]["run_number"]

                # Initialize failed with False
                failed = False
                try:
                    # emit signals to make bricks happy
                    osc_id, sample_id, sample_code, sample_location = self.update_oscillations_history(data_collect_parameters)
                    self.emit('collectOscillationStarted', (owner, sample_id, sample_code, sample_location, data_collect_parameters, osc_id))
                    data_collect_parameters["status"]='Running'
                  
                    # now really start collect sequence
                    print("*******************************************************************************************")
                    print("LNLSMultiCollect - calling do_collect()")
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
                                                 data_collect_parameters.get("sample_reference", {}).get("cell", ""))
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

            # Cleanup of temporary folder
            self.detector_hwobj.cleanup_remote_folder(os.path.join(self.detector_hwobj.get_pilatus_server_storage_temp(), os.getenv("USER")))
        finally:
            self.emit("collectEnded", owner, not failed, failed_msg if failed else "Data collection successful")
            logging.getLogger('HWR').info("data collection successful in loop")
            self.emit("collectReady", (True, ))

    @task
    def take_crystal_snapshots(self, number_of_snapshots):
        self.bl_control.diffractometer.takeSnapshots(number_of_snapshots, wait=True)

    @task
    def data_collection_hook(self, data_collect_parameters):
        """
        Descript. : 
        """
        p = data_collect_parameters

        # Parameters read from user interface
        filePath = str(p["fileinfo"]["directory"]) + "\0"
        filePath = filePath.replace(self.detector_hwobj.get_pilatus_server_storage(), self.detector_hwobj.get_pilatus_server_storage_temp())
        fileName = str(p["fileinfo"]["prefix"]) + "_" + str(p["fileinfo"]["run_number"]) + "." + str(self.fileSuffix()) + "\0"
        #fileTemplate = str(p['fileinfo']['template']) + "\0"
        # e.g.: test9_mx1_1_%04d.cbf
        fileTemplate = str("%s%s." + self.fileSuffix() + "\0")
        acquireTime = p['oscillation_sequence'][0]['exposure_time']
        numImages   = p['oscillation_sequence'][0]['number_of_images']
        startAngle = p['oscillation_sequence'][0]['start']
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
        self._total_time_redout = ((acquireTime + 0.0023) * numImages)
        oscilationVelo      = (self._total_angle / self._total_time)     # degrees per second
        oscilationVeloRPM   = (oscilationVelo * 60 / 360)                # RPM
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

        # Store previous Omega velocity
        self._previous_omega_velo = self.diffractometer_hwobj.get_omega_velocity()

        # Open shutter
        #self.detector_hwobj.open_shutter()

        # Set Omega velocity (RPM) for acquisition
        self.diffractometer_hwobj.set_omega_velocity(oscilationVeloRPM)

        # Send command to move omega
        #self.diffractometer_hwobj.move_omega_absolute(self._total_angle)

        # Send command to start acquisition
        self.detector_hwobj.acquire()

        # Close shutter
        #self.detector_hwobj.open_shutter()

        # Reload previous Omega velocity
        #self.diffractometer_hwobj.set_omega_velocity(self._previous_omega_velo)

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
        print("*******************************************************************************************")
        print("LNLSMultiCollect - set_wavelength")
        self.energy_hwobj.setWavelength(wavelength)

    def set_energy(self, energy):
        print("*******************************************************************************************")
        print("LNLSMultiCollect - set_energy")
        self.energy_hwobj.setEnergy(energy)

    @task
    def set_resolution(self, new_resolution):
        return

    @task
    def move_detector(self, detector_distance):
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
    def open_safety_shutter(self):
        # Open detector shutter
        self.detector_hwobj.open_shutter()
        # Send a comand to move omega
        self.diffractometer_hwobj.move_omega_absolute(self._total_angle)

        # Schedule the close shutter task to be executed at the end of all acquisitions        
        try:
            self.__safety_shutter_close_task = gevent.spawn_later(self._total_time_redout + 1, self.close_safety_shutter, timeout=10)
        except:
            logging.exception("Could not close safety shutter")

    def safety_shutter_opened(self):
        return self.detector_hwobj.shutter_opened()

    @task
    def close_safety_shutter(self):
        # Close detector shutter
        self.detector_hwobj.close_shutter()
        # Restore omega motor velocity
        self.diffractometer_hwobj.set_omega_velocity(self._previous_omega_velo)
        # Send a comand to move omega back to its initial position
        self.diffractometer_hwobj.move_omega_absolute(self._initial_angle)

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
        return
      
    def write_image(self, last_frame):
        self.actual_frame_num += 1
        return

    def last_image_saved(self):
        return self.actual_frame_num

    def stop_acquisition(self):
        return 
      
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
            return self.beam_info_hwobj.get_beam_position()
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


    """
    processDataScripts
        Description    : executes a script after the data collection has finished
        Type           : method
    """
    def trigger_auto_processing(self, process_event, xds_dir, EDNA_files_dir=None, anomalous=None, residues=200, do_inducedraddam=False, spacegroup=None, cell=None, frame=None):
        # Perform the copy of CBF file from temporary to definite place in storage
        try:
            if (frame):
                filePathDest = self._file_directory
                filePathOrig = filePathDest.replace(self.detector_hwobj.get_pilatus_server_storage(), self.detector_hwobj.get_pilatus_server_storage_temp())

                copied = False
                tries = 0

                while ((copied == False) and (tries < MAXIMUM_TRIES_COPY_CBF)):
                    for cbfFile in glob.glob(os.path.join(filePathOrig, str(self._file_prefix) + "_" + str(self._file_run_number) + "*" + str(frame -1).zfill(5) + "." + str(self.fileSuffix()))):
                        shutil.copy(cbfFile, filePathDest)

                        copied = True

                    if (not copied):
                        tries += 1
                        # A short sleep to be sure the files will be there
                        gevent.sleep(0.01)
        except:
            logging.getLogger("HWR").exception("Error when copying CBF files")

        # Call parent method
        AbstractMultiCollect.trigger_auto_processing(self, process_event, xds_dir, EDNA_files_dir, anomalous, residues, do_inducedraddam, spacegroup, cell, frame)