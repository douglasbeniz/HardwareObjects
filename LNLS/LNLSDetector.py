"""
Detector hwobj maintains information about detector.
"""
from HardwareRepository.BaseHardwareObjects import Equipment
import os
import re
import logging 
import paramiko
import pexpect
import subprocess
import gevent

from gevent import monkey
from time import sleep
from datetime import datetime

# This was necessary because of paramiko.ssh_exception.SSHException when running the procedure of cleanup
monkey.patch_all()

from py4syn.epics.PilatusClass import Pilatus
from py4syn.epics.ShutterClass import SimpleShutter


TIMEOUT_CAMSERVER_CONNECTION    = 120
TOLERANCE_THRESHOLD             = 0.01      # 10 eV


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

        self.wait_threshold = 40        # time to wait for camServer to set Pilatus Threshold
        self.starting_camserver = False

        self.distance_motor_hwobj = None

        self.chan_temperature = None
        self.chan_humidity = None
        self.chan_status = None
        self.chan_detector_mode = None
        self.chan_frame_rate = None

        self.ssh_det = None
        self.ssh_usermx2 = None

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

        # Connect signals to related objects
        if (self.distance_motor_hwobj):
            self.distance_motor_hwobj.connect('positionChanged', self.detectorDistanceChanged)
            self.distance_motor_hwobj.connect('stateChanged', self.detectorStateChanged)

    def get_radius(self):
        """
        Descript. : Parameter specific to Detector, from XML
        """
        return self.pilatusHalfOfHeight

    def get_collect_name(self):
        """
        Descript. :
        """
        return self.detector_collect_name

    def get_shutter_name(self):
        """
        Descript. :
        """
        return self.detector_shutter_name
        
    def get_distance(self):
        """
        Descript. : 
        """
        if self.distance_motor_hwobj:
            return self.distance_motor_hwobj.getPosition()

    def detectorDistanceChanged(self, value):
        self.emit('positionChanged', (value))

    def detectorStateChanged(self, value):
        self.emit('stateChanged', (value))

    def move_detector_distance(self, distance, wait=False):
        if self.distance_motor_hwobj:
            try:
                self.distance_motor_hwobj.move(absolutePosition=distance, wait=wait)
            except:
                logging.getLogger().exception("error while moving detector distance")
        else:
            logging.getLogger().exception("no distance motor configure in detector object!")

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
        return self.shutter_pilatus.isOpen()

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

    def stop(self):
        """
        Description. : Stop the acquisition on Pilatus
        """
        self.detector_pilatus.stopCount()

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


    def set_threshold(self, threshold, wait=True, force=False):
        changed = False 

        if (force or (threshold < (self.get_threshold() - TOLERANCE_THRESHOLD)) or (threshold > (self.get_threshold() + TOLERANCE_THRESHOLD))):
            logging.getLogger("user_level_log").error('Changing Pilatus threshold to %.3f, please, this should take around 1 minute.' % (threshold))

            # Start
            startToChangeThreshold = datetime.now()

            self.detector_pilatus.setThreshold(threshold, wait=wait)

            # End after set via py4syn...
            endToChangeThreshold = datetime.now()
            # 
            deltaTimeThreshold = endToChangeThreshold - startToChangeThreshold
            deltaTimeThreshold = deltaTimeThreshold.total_seconds()

            remainingTimeToWait = (self.wait_threshold - deltaTimeThreshold)
            # 
            if (remainingTimeToWait > 0):
                if (wait):
                    self.wait_setting_threshold(remainingTimeToWait)
                else:
                    gevent.spawn(self.wait_setting_threshold, remainingTimeToWait)

            changed = True

        return changed


    def wait_setting_threshold(self, timeToWait):
        gevent.sleep(timeToWait)
        # Informing user we finished
        logging.getLogger("user_level_log").info('New Pilatus threshold set to %.3f!' % (self.get_threshold()))


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

    def get_det_2_theta(self):
        return self.detector_pilatus.getDet2Theta()

    def get_pilatus_server_storage_temp(self):
        return self.pilatusServerStorageTemp

    def get_pilatus_server_storage(self):
        return self.pilatusServerStorage

    def get_camserver_screenshot_name(self):
        return self.camserverScreenshotName


    def get_readout_per_image(self):
        if (self.readoutPerImage):
            return float(self.readoutPerImage)
        else:
            return 0.0

    def is_camserver_connected(self):
        return self.detector_pilatus.isCamserverConnected()


    def is_starting_camserver(self):
        return self.starting_camserver


    def is_counting(self):
        return self.detector_pilatus.isCounting()


    def cleanup_remote_folder(self, folder):
        try:
            # Connect to Pilatus server using defined parameters
            ssh = self.stablishSSHConnection()
            # Send a command to remove entire folder
            stdin, stdout, stderr = ssh.exec_command("rm -rf " + str(folder))
            ssh.close()

            if (self.ssh_det is not None):
                self.ssh_det.close()
                self.ssh_det = None

            if (self.ssh_usermx2 is not None):
                self.ssh_usermx2.close()
                self.ssh_usermx2 = None
        except:
            error_message = "Error when trying to cleanup temporary folder on pilatus server..."
            logging.getLogger().exception(error_message)
            logging.getLogger("user_level_log").error(error_message)


    def change_file_owner(self, fullFileName, owner):
        try:
            # Connect to Pilatus server using defined parameters
            ssh = self.stablishSSHConnection()

            # Send a command to change the owner of folder
            #stdin, stdout, stderr = ssh.exec_command("sudo chown %s:domain^users %s" % (owner, os.path.split(fullFileName)[0]))
            # Send a command to change the owner of file
            stdin, stdout, stderr = self.ssh_det.exec_command("sudo chown %s:domain^users %s" % (owner, fullFileName))
            ssh.close()
        except:
            error_message = "Error when trying to change owner on pilatus server..."
            logging.getLogger().exception(error_message)
            logging.getLogger("user_level_log").error(error_message)


    def change_file_owner_and_move(self, fullFileNameOrig, fullPathDest, owner):
        try:
            # Connect to Pilatus server using defined parameters
            if (self.ssh_det is None):
                self.ssh_det = self.stablishSSHConnection()

            # Send a command to change the owner of folder
            #stdin, stdout, stderr = ssh.exec_command("sudo chown %s:domain^users %s" % (owner, os.path.split(fullFileName)[0]))
            # Send a command to change the owner of file
            stdin, stdout, stderr = self.ssh_det.exec_command("sudo chown %s:domain^users %s" % (owner, fullFileNameOrig))

            # Wait ps command to complete
            #while not stdout.channel.exit_status_ready():
            #    gevent.sleep(0.01)

            #ssh.close()

            if (self.ssh_usermx2 is None):
                self.ssh_usermx2 = self.stablishSSHConnection(user="usermx2", password="B@tatinha123")

            stdin, stdout, stderr = self.ssh_usermx2.exec_command("cp %s %s" % (fullFileNameOrig, fullPathDest))

            # Wait ps command to complete
            #while not stdout.channel.exit_status_ready():
            #    gevent.sleep(0.01)

            # Check that no error occurred, what means that a 'copy' was done
            # print("**********************")
            # print("SSH")
            # print(fullFileNameOrig)
            # print(fullPathDest)
            # print("recv_stderr_ready(): ", stdout.channel.recv_stderr_ready())
            # print("recv_exit_status(): ", stdout.channel.recv_exit_status())
            # print("**********************")
            result = not stdout.channel.recv_stderr_ready()
            #ssh.close()

            return result
        except:
            error_message = "Error when trying to change owner on pilatus server and copy file..."
            logging.getLogger().exception(error_message)
            logging.getLogger("user_level_log").error(error_message)

            return False


    def start_camserver_if_not_connected(self):
        if (not self.starting_camserver):
            gevent.spawn(self.process_start_camserver_if_not_connected)


    def process_start_camserver_if_not_connected(self):
        camserverIsRunning = True
        self.starting_camserver = True

        try:
            # Check if Pilatus IOC is not connected before to proceed
            if (not self.is_camserver_connected()):
                error_message =  "CamServer is not running... Trying to start it... Please, wait a while..."
                logging.getLogger("user_level_log").error(error_message)

                # Connect to Pilatus server using defined parameters
                ssh = self.stablishSSHConnection()

                # --------------------------------------------------------------
                # Stop previous running 'camserver' through 'xpra'
                # --------------------------------------------------------------
                # First, try to access the camserver and send 'exit' command through 'xpra'
                stdin, stdout, stderr = ssh.exec_command("ps -ef | grep %s | grep -v grep" % (self.camserverXpraProgram))

                # Wait ps command to complete
                while not stdout.channel.exit_status_ready():
                    gevent.sleep(0.1)

                # Check if no error occurred, what means that an 'xpra' process was found
                if (not stdout.channel.recv_exit_status()):
                    # Call the method to try stop 'camserver' using 'xpra'...
                    self.stop_camserver()

                # --------------------------------------------------------------
                # If trying of stop 'camserver' (self.camserverUniqueName) through 'xpra' failed, then kill the processes, if still any
                # --------------------------------------------------------------
                # No 'xpra' process found, or it was not able to send 'exit' command to camserver.
                # Check if no 'camserver' is still running...
                stdin, stdout, stderr = ssh.exec_command("ps -ef | grep %s | grep -v grep" % (self.camserverUniqueName))

                # Wait ps command to complete
                while not stdout.channel.exit_status_ready():
                    gevent.sleep(0.1)

                # Check that no error occurred, what means that a 'camserver' process was found
                if (not stdout.channel.recv_exit_status()):
                    # Parse returned processes
                    process_list = stdout.read().decode('ascii').split('\n')

                    # If exist any processing 'camserver', force stopping all of them using 'kill'
                    if (len(process_list) > 1):
                        stdin, stdout, stderr = ssh.exec_command("ps -ef | grep %s | grep -v grep | awk {\'print $2\'} | xargs kill -s 2" % (self.camserverUniqueName))
                        # Wait ps command to complete
                        while not stdout.channel.exit_status_ready():
                            gevent.sleep(0.1)

                        # Check if some error occurred
                        if (stdout.channel.recv_exit_status()):
                            error_message = "Error when trying to kill \'%s\' processes! %s" % (self.camserverUniqueName, stderr.read().decode('ascii'))
                            logging.getLogger().exception(error_message)
                            logging.getLogger("user_level_log").error(error_message)
                else:
                    error_message = "No existing \'%s\' process running! %s" % (self.camserverUniqueName, stderr.read().decode('ascii'))
                    logging.getLogger().exception(error_message)

                # --------------------------------------------------------------
                # Stop previous running 'xpra' (self.camserverXpraProgram), if any
                # --------------------------------------------------------------
                self.stopXpra(ssh=ssh)

                # --------------------------------------------------------------
                # Finally, start a new 'xpra' instance controlling 'camserver' program
                # --------------------------------------------------------------
                # Send a command to start Xpra with camonly script
                #stdin, stdout, stderr = ssh.exec_command("dbus-launch xpra --bind-tcp=0.0.0.0:%s --no-daemon --start-child=%s start :%s" % (self.camserverXpraPort, self.camserverCamonlyProgram, self.camserverXpraDisplay))
                stdin, stdout, stderr = ssh.exec_command("dbus-launch xpra --bind-tcp=0.0.0.0:%s --start-child=%s start :%s" % (self.camserverXpraPort, self.camserverCamonlyProgram, self.camserverXpraDisplay))

                gevent.sleep(1)

                # Check if xpra was started...
                stdin, stdout, stderr = ssh.exec_command("ps -ef | grep %s | grep -v grep" % (self.camserverXpraProgram))

                # Wait ps command to complete
                while not stdout.channel.exit_status_ready():
                    gevent.sleep(0.1)

                # Check that an error OCCURRED, what means that a 'xpra' process was NOT found
                if (stdout.channel.recv_exit_status()):
                    camserverIsRunning = False
                    # Inform the problem...
                    error_message = "Error when trying to start \'%s\' on pilatus server... %s" % (self.camserverUniqueName, stderr.read().decode('ascii'))
                    logging.getLogger().exception(error_message)
                    logging.getLogger("user_level_log").error("-------------------------------------------------------------------")
                    logging.getLogger("user_level_log").error(error_message)
                    logging.getLogger("user_level_log").error("-------------------------------------------------------------------")
                else:
                    # Confirm thad Pilatus AreaDetector connected to CamServer...
                    tries = 0
                    while (not self.is_camserver_connected() and (tries < TIMEOUT_CAMSERVER_CONNECTION)):
                        gevent.sleep(1)

                    if (self.is_camserver_connected()):
                        # Inform user that CamServer has been started!
                        info_message = "Successfully started \'%s\' process!" % (self.camserverUniqueName)
                        logging.getLogger("user_level_log").info("-------------------------------------------------------------------")
                        logging.getLogger("user_level_log").info(info_message)
                        logging.getLogger("user_level_log").info("-------------------------------------------------------------------")

                # Then close the connection
                ssh.close()

                if (camserverIsRunning):
                    # (Re)set threshold on CamServer everytime it is (re)started
                    #self.set_threshold(self.get_threshold(), wait=True, force=True)
                    self.set_threshold(self.get_threshold(), wait=False, force=True)

                # Reset flag to indicate camserver initialization
                self.starting_camserver = False
        except:
            if ssh:
                # Stop SSH connection
                ssh.close()

            camserverIsRunning = False
            # Reset flag to indicate camserver initialization
            self.starting_camserver = False

            error_message = ("Error when trying to start \'%s\' on pilatus server..." % (self.camserverUniqueName))
            logging.getLogger().exception(error_message)
            logging.getLogger("user_level_log").error("-------------------------------------------------------------------")
            logging.getLogger("user_level_log").error(error_message)
            logging.getLogger("user_level_log").error("-------------------------------------------------------------------")

        # -------------------------------------------------
        # Return if successfully started, it was already running, camserver
        return (camserverIsRunning and self.is_camserver_connected())

    def stop_camserver(self, image_path="."):
        stopped = False

        try:
            # Getting the execution of camserver on remote Pilatus server to be displayed locally
            pexpt_xpra = pexpect.spawn("xpra attach tcp:%s:%s" % (self.pilatusServerIP, self.camserverXpraPort))
            # Using Wmctrl command to get display where camserver is running locally
            display = subprocess.check_output("wmctrl -lp | grep \'%s\' | awk \'{print $1}\'" % (self.camserverUniqueName), shell=True)
            display = display.decode('ascii').split('\n')[0]

            # Check that a display was found...
            if (display):
                # Write the exit command on camserver terminal
                os.system("xdotool windowfocus --sync %s; xdotool type \'%s\'; xdotool key KP_Enter" % (display, self.camserverExitCommand))
                # Take a screenshot...
                self.takeScreenshotOfXpraRunningProcess(image_path=image_path)
                # Wait a while and retry the exit command, because more than one terminal could be running
                gevent.sleep(0.1)
                os.system("xdotool windowfocus --sync %s; xdotool type \'%s\'; xdotool key KP_Enter" % (display, self.camserverExitCommand))

                stopped = True

            # Send Ctrl+C to Xpra and detach from remote display
            pexpt_xpra.send("\003")
            # Stop Pexpect connection
            pexpt_xpra.close()

            # --------------------------------------------------------------
            # Try to stop xpra running on Pilatus server
            # --------------------------------------------------------------
            # Connect to Pilatus server using defined parameters
            ssh = self.stablishSSHConnection()
            # Call a procedure to stop xpra...
            self.stopXpra(ssh=ssh)
            # Then close the connection
            ssh.close()

        except:
            if pexpt_xpra:
                # Stop Pexpect connection
                pexpt_xpra.close()

            if ssh:
                # Stop SSH connection
                ssh.close()

            error_message = "Error when trying to stop camserver on pilatus server..."
            logging.getLogger().exception(error_message)
            logging.getLogger("user_level_log").error(error_message)

        # Inform if had a chance to send 'exit' command through the display
        return stopped


    def stopXpra(self, ssh):
        # --------------------------------------------------------------
        # Stop previous running 'xpra' (self.camserverXpraProgram), if any
        # --------------------------------------------------------------
        # Check if no 'xpra' is running
        stdin, stdout, stderr = ssh.exec_command("ps -ef | grep %s | grep -v grep" % (self.camserverXpraProgram))

        # Wait ps command to complete
        while not stdout.channel.exit_status_ready():
            gevent.sleep(0.1)

        # Check that no error occurred, what means that a 'xpra'process was found
        if (not stdout.channel.recv_exit_status()):
            # Send a command to stop Xpra sessions
            stdin, stdout, stderr = ssh.exec_command("xpra stop")

            # Wait ps command to complete
            while not stdout.channel.exit_status_ready():
                gevent.sleep(0.1)

            # Check if any error occurred...
            if (stdout.channel.recv_exit_status()):
                # Check if any xpra is still running...
                stdin, stdout, stderr = ssh.exec_command("ps -ef | grep %s | grep -v grep" % (self.camserverXpraProgram))

                # Wait ps command to complete
                while not stdout.channel.exit_status_ready():
                    gevent.sleep(0.1)

                # Check that no error occurred, what means that a 'xpra' process was found
                if (not stdout.channel.recv_exit_status()):
                    # Force 'xpra' to stop through 'kill'...
                    stdin, stdout, stderr = ssh.exec_command("ps -ef | grep %s | grep -v grep | awk {\'print $2\'} | xargs kill -s 2" % (self.camserverXpraProgram))

                    # Wait ps command to complete
                    while not stdout.channel.exit_status_ready():
                        gevent.sleep(0.1)

                    # Check if some error beam_crystal_position
                    if (stdout.channel.recv_exit_status()):
                        error_message = "Error when trying to kill running \'%s\' processes! %s" % (self.camserverXpraProgram, stderr.read().decode('ascii'))
                        logging.getLogger().exception(error_message)
                        logging.getLogger("user_level_log").error(error_message)
            else:
                error_message = "Previous \'%s\' process was successfully stopped!" % (self.camserverXpraProgram)
                logging.getLogger().exception(error_message)
        else:
            error_message = "No existing \'%s\' process running! %s" % (self.camserverXpraProgram, stderr.read().decode('ascii'))
            logging.getLogger().exception(error_message)


    def takeScreenshotOfXpraRunningProcess(self, image_path='.', run_number="1", image_extension='.png'):
        try:
            # Connect to Pilatus server using defined parameters
            ssh = self.stablishSSHConnection()

            # Guarantee unique names of images
            fileName = self.createUniqueFileName(name=os.path.join(image_path, self.camserverScreenshotName + "_" + str(run_number) + image_extension))
            # print("# ********")
            # print("Camserver screenshot: ", fileName)
            # print("# ********")

            # Check locally maped MX2Temp storage folder which should be the same as remote mapping on Pilatus server
            if (not os.path.exists(image_path)):
                try:
                    # Send a command to remove entire folder
                    stdin, stdout, stderr = ssh.exec_command("mkdir -p %s" % (image_path))

                    # Wait ps command to complete
                    while not stdout.channel.exit_status_ready():
                        gevent.sleep(0.1)

                    # Check if an error occurred
                    if (stdout.channel.recv_exit_status()):
                        logging.getLogger().error("Snapshot: error trying to create the directory %s (%s)" % (logFilePath, str(diag)))

                    # # Wait a while to guarantee the folder is accessible
                    # gevent.sleep(1)

                except OSError as diag:
                    logging.getLogger().error("Snapshot: error trying to create the directory %s (%s)" % (logFilePath, str(diag)))

            # Send a command to remove entire folder
            stdin, stdout, stderr = ssh.exec_command("xpra screenshot %s" % (fileName))

            # Wait ps command to complete
            while not stdout.channel.exit_status_ready():
                gevent.sleep(0.1)

            # Check if an error occurred
            if (stdout.channel.recv_exit_status()):
                error_message = "Error when trying to take a snapshot of running camserver process..." + stderr.read().decode('ascii')
                logging.getLogger().exception(error_message)
                #logging.getLogger("user_level_log").error(error_message)

            ssh.close()
        except:
            if ssh:
                # Stop SSH connection
                ssh.close()

            error_message = "Error when trying to take a snapshot of running camserver process..."
            logging.getLogger().exception(error_message)
            #logging.getLogger("user_level_log").error(error_message)


    def createUniqueFileName(self, name):
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

        return newName


    def stablishSSHConnection(self, user=None, password=None):
        # Instantiate a paramiko object
        ssh = paramiko.SSHClient()
        # If server is not in knowm_hosts it will be included
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # Connect
        if (user is None and password is None):
            ssh.connect(self.pilatusServerIP, username=self.pilatusSshUser, password=self.pilatusSshPassword, timeout=10)
        else:
            ssh.connect(self.pilatusServerIP, username=user, password=password, timeout=10)

        return ssh


    def update_values(self):
        # Call the update of Detector
        self.distance_motor_hwobj.update_values()
