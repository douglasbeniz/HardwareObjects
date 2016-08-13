"""
Detector hwobj maintains information about detector.
"""
from HardwareRepository.BaseHardwareObjects import Equipment
import logging 
import paramiko
from gevent import monkey

# This was necessary because of paramiko.ssh_exception.SSHException when running the procedure of cleanup
monkey.patch_all()

from py4syn.epics.PilatusClass import Pilatus
from py4syn.epics.ShutterClass import SimpleShutter

class LNLSDetector(Equipment):
    TRIGGER_MODE = { "Internal":        0,
                     "Ext. Enable":     1,
                     "Ext. Trigger":    2,
                     "Mult. Trigger":   3,
                     "Alignment":       4 }
    """
    Descript. : Detector class. Contains all information about detector
                the states are 'OK', and 'BAD'
                the status is busy, exposing, ready, etc.
                the physical property is RH for pilatus, P for rayonix
    """
    def __init__(self, name): 
        """
        Descript. :
        """ 
        Equipment.__init__(self, name)

        self.temperature = 23
        self.humidity = 50
        self.tolerance = 0.1
        self.detector_mode = 0
        self.detector_modes_dict = None
        self.detector_collect_name = None
        self.detector_shutter_name = None
        self.temp_treshold = None
        self.hum_treshold = None   
        self.exp_time_limits = None

        self.distance_motor_hwobj = None

        self.chan_temperature = None
        self.chan_humidity = None
        self.chan_status = None
        self.chan_detector_mode = None
        self.chan_frame_rate = None

    def init(self):
        """
        Descript. :
        """
        # Related hardware objects
        self.distance_motor_hwobj = self.getObjectByRole("distance_motor")

        # Related properties
        self.detector_collect_name = self.getProperty("collectName")
        self.detector_shutter_name = self.getProperty("shutterName")
        self.tolerance = self.getProperty("tolerance")
        self.temp_treshold = self.getProperty("tempThreshold") 
        self.hum_treshold = self.getProperty("humidityThreshold")

        try:
           self.detector_modes_dict = eval(self.getProperty("detectorModes"))
        except:
           pass

        # Instantiating a Pilatus device
        self.detector_pilatus = Pilatus('Pilatus', self.pilatusEpicsAddress)
        self.shutter_pilatus = SimpleShutter('ShutterPilatus', self.shutterEpicsAddress, invert=True)

    def get_collect_name(self):
        """
        Descript. :
        """
        return self.detector_collect_name

    def get_shutter_name(self):
        """
        Desccript. :
        """
        return self.detector_shutter_name
        
    def get_distance(self):
        """
        Descript. : 
        """
        if self.distance_motor_hwobj:
            return self.distance_motor_hwobj.getPosition()

    def set_detector_mode(self, mode):
        """
        Descript. :
        """
        return

    def get_detector_mode(self):
        """
        Descript. :
        """
        return self.detector_mode

    def default_mode(self):
        return 1

    def get_detector_modes_list(self):
        """
        Descript. :
        """
        if self.detector_modes_dict is not None:
            return list(self.detector_modes_dict.keys())    
        else:
            return [] 

    def has_shutterless(self):
        """
        Description. :
        """
        return self.getProperty("hasShutterless")

    def open_shutter(self):
        self.shutter_pilatus.open()

    def close_shutter(self):
        self.shutter_pilatus.close()

    def shutter_opened(self):
        self.shutter_pilatus.isOpen()

    def get_exposure_time_limits(self):
        """
        Description. :
        """
        return self.exp_time_limits

    def acquire(self):
        """
        Description. :  Set Acquire PV of Pilatus AreaDetector to 1, then start to acquire
        """
        self.detector_pilatus.startCount()

    def set_file_path(self, path):
        self.detector_pilatus.setFilePath(path)

    def get_file_path(self):
        return self.detector_pilatus.getFilePath()

    def set_file_name(self, name):
        self.detector_pilatus.setFileName(name)

    def get_file_name(self):
        return self.detector_pilatus.getFileName()

    def set_file_template(self, template="%s%s"):
        self.detector_pilatus.setFileTemplate()

    def get_file_template(self):
        return self.detector_pilatus.getFileTemplate()

    def set_acquire_time(self, time):
        self.detector_pilatus.setCountTime(time)

    def get_acquire_time(self):
        return self.detector_pilatus.getAcquireTime()

    def set_acquire_period(self, period):
        self.detector_pilatus.setAcquirePeriod(period)

    def get_acquire_period(self):
        return self.detector_pilatus.getAcquirePeriod()

    def set_threshold(self, threshold):
        self.detector_pilatus.setThreshold(threshold)

    def get_threshold(self):
        return self.detector_pilatus.getThreshold()

    def set_beam_position(self, position=[0, 0]):
        self.detector_pilatus.setBeamPosition(position)

    def get_beam_position(self):
        return self.detector_pilatus.getBeamPosition()

    def set_wavelength(self, wavelength):
        self.detector_pilatus.setWavelength(wavelength)

    def get_wavelength(self):
        return self.detector_pilatus.getWavelength()

    def set_start_angle(self, angle):
        self.detector_pilatus.setStartAngle(angle)

    def get_start_angle(self):
        return self.detector_pilatus.getStartAngle()

    def set_angle_incr(self, incr):
        self.detector_pilatus.setAngleIncr(incr)

    def get_angle_incr(self):
        return self.detector_pilatus.getAngleIncr()

    def set_det_dist(self, distance):
        self.detector_pilatus.setDetDist(distance)

    def get_det_dist(self):
        return self.detector_pilatus.getDetDist()

    def set_num_images(self, num):
        self.detector_pilatus.setNumImages(num)

    def get_num_images(self):
        return self.detector_pilatus.getNumImages()

    def set_delay_time(self, delay):
        self.detector_pilatus.setDelayTime(delay)

    def get_delay_time(self):
        return self.detector_pilatus.getDelayTime()

    # mode can be one of LNLSDetector.TRIGGER_MODE options
    def set_trigger_mode(self, mode):
        self.detector_pilatus.setTriggerMode(mode)

    def get_trigger_mode(self):
        return self.detector_pilatus.getTriggerMode()

    def set_det_2_theta(self, det2theta):
        self.detector_pilatus.setDet2Theta(det2theta)

    def get_det_2_theat(self):
        return self.detector_pilatus.getDet2Theta()

    def get_pilatus_server_storage_temp(self):
        return self.pilatusServerStorageTemp

    def get_pilatus_server_storage(self):
        return self.pilatusServerStorage

    def cleanup_remote_folder(self, folder):
        try:
            ssh = paramiko.SSHClient()
            # If server is not in knowm_hosts it will be included
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # Conncet
            ssh.connect(self.pilatusServerIP, username=self.pilatusSshUser, password=self.pilatusSshPassword)
            # Send a command to remove entire folder
            stdin, stdout, stderr = ssh.exec_command("rm -rf " + str(folder))
            ssh.close()
        except:
            print("ERROR trying to cleanup temporary folder in pilatus server...")
