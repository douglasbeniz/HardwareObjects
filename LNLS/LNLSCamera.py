"""
Class for cameras connected by EPICS Device Server
"""
from HardwareRepository import BaseHardwareObjects
import logging
import os
from io import BytesIO
import gevent
import time
import numpy
from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt4 import QtGui, QtCore
import io

#-----------------------------------------------------------------------------
CAMERA_DATA          = "epicsCameraSample_data"
CAMERA_BACK          = "epicsCameraSample_back"
CAMERA_EN_BACK       = "epicsCameraSample_en_back"
CAMERA_ACQ_START     = "epicsCameraSample_acq_start"
CAMERA_ACQ_STOP      = "epicsCameraSample_acq_stop"
CAMERA_GAIN          = "epicsCameraSample_gain"
CAMERA_GAIN_RBV      = "epicsCameraSample_gain_rbv"
CAMERA_AUTO_GAIN     = "epicsCameraSample_auto_gain"
CAMERA_AUTO_GAIN_RBV = "epicsCameraSample_auto_gain_rbv"
CAMERA_FPS_RBV       = "epicsCameraSample_frames_per_second_rbv"
CAMERA_ACQ_TIME      = "epicsCameraSample_acq_time"
CAMERA_ACQ_TIME_RBV  = "epicsCameraSample_acq_time_rbv"

ARRAY_SIZE = 1280*1024*32/8
#-----------------------------------------------------------------------------
class LNLSCamera(BaseHardwareObjects.Device):

    def __init__(self,name):
        BaseHardwareObjects.Device.__init__(self,name)
        self.liveState = False
        self.refreshing = False

        self.imagegen = None
        self.refreshgen = None

        self.imgArray = None
        self.qImage = None
        self.qImageHalf = None
        self.qtPixMap = None


    def _init(self):
        self.setIsReady(True)


    def init(self):
        # Start camera image acquisition
        self.setLive(True)

        # Snapshot
        self.centring_status = {"valid": False}
        self.snapshots_procedure = None


    def imageGenerator(self, delay):
        while self.liveState:
            self.getCameraImage()
            gevent.sleep(delay)


    def getCameraImage(self):
        # Get the image from uEye camera IOC
        self.imgArray = self.getValue(CAMERA_DATA)

        if ((self.imgArray is None) or (len(self.imgArray) != ARRAY_SIZE)):
            logging.getLogger().exception("%s - Error in array lenght!" % (self.__class__.__name__))
            logging.getLogger("user_level_log").error("Impossible to refresh camera!")
            # Stop camera to be in live mode
            self.liveState = False
            return -1

        # self.qImage has 1280 x 1024 size (width x height)
        self.qImage = QtGui.QImage(self.imgArray, 1280, 1024, 1280*32/8, QtGui.QImage.Format_RGB32)
        self.imgArray = None

        try:
            self.qTransform = QtGui.QTransform()
            self.qTransform.rotate(90)

            # self.qImage now has 1024 x 1280 size (width x height)
            self.qImage = self.qImage.transformed(self.qTransform)

            # self.qImage now has 640 x 800 size (width x height)
            self.qImageHalf = self.qImage.scaledToWidth(640);

            # Clear memory
            self.qImage = None

            # Resize - OBSOLETE
            #self.qImageHalf = self.qImage.scaled(640, 512, QtCore.Qt.KeepAspectRatioByExpanding)

            # Crop image, position (x, y) = 0, 144; (w, h) =  640, 512
            # the size of image rectangle in UI
            self.qImageCropped = self.qImageHalf.copy(0, 144, 640, 512)

            # Clear memory
            self.qImageHalf = None

            if (self.refreshing):
                logging.getLogger("user_level_log").info("Camera was refreshed!")
                self.refreshing = False
        except:
            logging.getLogger().exception("%s - Except in scale and rotate!" % (self.__class__.__name__))
            return -1

        self.qtPixMap = QtGui.QPixmap(self.qImageCropped)
        self.qImageCropped = None

        self.emit("imageReceived", self.qtPixMap)

        # Keep qtPixMap available for snapshot... do do NOT set it to 'None'
        #self.qtPixMap = None
        
        return 0


    def getStaticImage(self):
        qtPixMap = QtGui.QPixmap(self.source, "1")
        self.emit("imageReceived", qtPixMap)

    def get_image_dimensions(self):
        return (640*512)

    def getWidth(self):
        # X
        return 640

    def getHeight(self):
        # Z
        return 512

    def contrastExists(self):
        return False

    def brightnessExists(self):
        return False

    def gainExists(self):
        return True

    def get_gain(self):
        gain = None

        try:
            gain = self.getValue(CAMERA_GAIN_RBV)
        except:
            print("Error getting gain of camera...")

        return gain

    def set_gain(self, gain):
        try:
            self.setValue(CAMERA_GAIN, gain)
        except:
            print("Error setting gain of camera...")


    def get_gain_auto(self):
        auto = None

        try:
            auto = self.getValue(CAMERA_AUTO_GAIN_RBV)
        except:
            print("Error getting auto-gain of camera...")

        return auto


    def set_gain_auto(self, auto):
        try:
            self.setValue(CAMERA_AUTO_GAIN, auto)
        except:
            print("Error setting auto-gain of camera...")


    def get_exposure_time(self):
        exp = None

        try:
            exp = self.getValue(CAMERA_ACQ_TIME_RBV)
        except:
            print("Error getting exposure time of camera...")

        return exp


    def set_exposure_time(self, exp):
        try:
            self.setValue(CAMERA_ACQ_TIME, exp)
        except:
            print("Error setting exposure time of camera...")


    def start_camera(self):
        try:
            self.setValue(CAMERA_BACK, 1)
            self.setValue(CAMERA_EN_BACK, 1)
            self.setValue(CAMERA_ACQ_STOP, 0)
            self.setValue(CAMERA_ACQ_START, 1)
        except:
            pass


    def stop_camera(self):
        try:
            self.setValue(CAMERA_ACQ_START, 0)
            self.setValue(CAMERA_ACQ_STOP, 1)
        except:
            pass


    def refresh_camera_procedure(self):
        self.refreshing = True

        # Try to reconnect to PVs
        self.reconnect(CAMERA_DATA)
        self.reconnect(CAMERA_BACK)
        self.reconnect(CAMERA_EN_BACK)
        self.reconnect(CAMERA_ACQ_START)
        self.reconnect(CAMERA_ACQ_STOP)
        self.reconnect(CAMERA_GAIN)
        self.reconnect(CAMERA_GAIN_RBV)
        self.reconnect(CAMERA_AUTO_GAIN)
        self.reconnect(CAMERA_AUTO_GAIN_RBV)
        self.reconnect(CAMERA_FPS_RBV)
        self.reconnect(CAMERA_ACQ_TIME)
        self.reconnect(CAMERA_ACQ_TIME_RBV)

        # Try to stop camera image acquisition
        self.setLive(False)
        # Wait a while
        gevent.sleep(0.2)
        # Set PVs to start
        self.start_camera()
        # (Re)start camera image acquisition
        self.setLive(True)


    def refresh_camera(self):
        logging.getLogger("user_level_log").error("Resetting camera, please, wait a while...")

        # Start a new thread to don't freeze UI
        self.refreshgen = gevent.spawn(self.refresh_camera_procedure)


    def setLive(self, live):
        try:
            if live and self.liveState == live:
                return
            
            if live:
                self.imagegen = gevent.spawn(self.imageGenerator, float(int(self.getProperty("interval"))/1000.0))
            else:
                if self.imagegen:
                    self.imagegen.kill()
                self.stop_camera()

            self.liveState = live

            return True
        except:
            return False


    def imageType(self):
        return None

    def takeSnapshot(self, *args):
        imgFile = QtCore.QFile(args[0])
        imgFile.open(QtCore.QIODevice.WriteOnly)
        self.qtPixMap.save(imgFile,"PNG")
        imgFile.close()


    def take_snapshots_procedure(self, image_count, snapshotFilePath, snapshotFilePrefix, logFilePath, runNumber, collectStart, collectEnd, motorHwobj, detectorHwobj):
        """
        Descript. : It takes snapshots of sample camera and camserver execution.
        """
        # Avoiding a processing of AbstractMultiCollect class for saving snapshots
        #centred_images = []
        centred_images = None
        positions = []

        try:
            # Calculate goniometer positions where to take snapshots
            if (collectEnd is not None and collectStart is not None):
                interval = (collectEnd - collectStart)
            else:
                interval = 0

            # To increment in angle increment
            increment = 0 if ((image_count -1) == 0) else (interval / (image_count -1))

            for incrementPos in range(image_count):
                if (collectStart is not None):
                    positions.append(collectStart + (incrementPos * increment))
                else:
                    positions.append(motorHwobj.getPosition())

            # Create folders if not found
            if (not os.path.exists(snapshotFilePath)):
                try:
                    os.makedirs(snapshotFilePath)
                except OSError as diag:
                    logging.getLogger().error("Snapshot: error trying to create the directory %s (%s)" % (snapshotFilePath, str(diag)))
            
            for index in range(image_count):
                while (motorHwobj.getPosition() < positions[index]):
                    gevent.sleep(0.02)

                logging.getLogger("HWR").info("%s - taking snapshot #%d" % (self.__class__.__name__, index + 1))

                # Save snapshot image file
                imageFileName = os.path.join(snapshotFilePath, snapshotFilePrefix + "_" + str(round(motorHwobj.getPosition(),2)) + "_" + motorHwobj.getEgu() + "_snapshot.png")

                #imageInfo = self.takeSnapshot(imageFileName)

                # This way all shapes will be also saved...
                self.emit("savaSnapshot", imageFileName)

                # Send a command to detector hardware-object to take snapshot of camserver execution...
                if (logFilePath and detectorHwobj):
                    detectorHwobj.takeScreenshotOfXpraRunningProcess(image_path=logFilePath, run_number=runNumber)

                #centred_images.append((0, str(imageInfo)))
                #centred_images.reverse() 
        except:
            logging.getLogger("HWR").exception("%s - could not take crystal snapshots" % (self.__class__.__name__))

        return centred_images


    def take_snapshots(self, image_count, snapshotFilePath, snapshotFilePrefix, logFilePath, runNumber, collectStart, collectEnd, motorHwobj, detectorHwobj, wait=False):
        """
        Descript. :  It takes snapshots of sample camera and camserver execution.
        """
        if image_count > 0:
            self.snapshots_procedure = gevent.spawn(self.take_snapshots_procedure, image_count, snapshotFilePath, snapshotFilePrefix, logFilePath, runNumber, collectStart, collectEnd, motorHwobj, detectorHwobj)

            self.centring_status["images"] = []

            self.snapshots_procedure.link(self.snapshots_done)

            if wait:
                self.centring_status["images"] = self.snapshots_procedure.get()


    def snapshots_done(self, snapshots_procedure):
        """
        Descript. :
        """
        try:
            self.centring_status["images"] = snapshots_procedure.get()
        except:
            logging.getLogger("HWR").exception("%s - could not take crystal snapshots" % (self.__class__.__name__))


    def cancel_snapshot(self):
        try:
            self.snapshots_procedure.kill()
        except:
            pass

    def __del__(self):
        logging.getLogger().exception("%s - __del__()!" % (self.__class__.__name__))
        self.stop_camera()
        self.setLive(False)
