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
CAMERA_DATA      = "epicsCameraSample_data"
CAMERA_BACK      = "epicsCameraSample_back"
CAMERA_EN_BACK   = "epicsCameraSample_en_back"
CAMERA_ACQ_START = "epicsCameraSample_acq_start"
CAMERA_ACQ_STOP  = "epicsCameraSample_acq_stop"

ARRAY_SIZE = 1280*1024*32/8
#-----------------------------------------------------------------------------
class LNLSCamera(BaseHardwareObjects.Device):

    def __init__(self,name):
        BaseHardwareObjects.Device.__init__(self,name)
        self.liveState = False

        self.imagegen = None

        self.imgArray = None
        self.qImage = None
        self.qImageHalf = None
        self.qtPixMap = None

        #self.channelCameraData = None

    def _init(self):
        self.setIsReady(True)

    def init(self):
        #self.channelCameraData = self.getChannelObject(CAMERA_DATA)

        #if (self.channelCameraData is not None):
        #    print("#################################################################################")
        #    print("self.channelCameraData is not None")
        #    print("#################################################################################")
        #    self.channelCameraData.connectSignal('update', self.getCameraImage)

        self.setLive(True)

    def imageGenerator(self, delay):
        while self.liveState:
            self.getCameraImage()
            gevent.sleep(delay)

    def getCameraImage(self):
        # Get the image from uEye camera IOC
        self.imgArray = self.getValue(CAMERA_DATA)

        if ((self.imgArray == None) or (len(self.imgArray) != ARRAY_SIZE)):
            print(" error in array lenght! %d" % len(self.imgArray))
            return -1

        self.qImage = QtGui.QImage(self.imgArray, 1280, 1024, 1280*32/8, QtGui.QImage.Format_RGB32)
        self.imgArray = None

        try:
            self.qTransform = QtGui.QTransform()
            self.qTransform.rotate(90)

            self.qImage = self.qImage.transformed(self.qTransform)

            self.qImageHalf = self.qImage.scaledToHeight(512);
            #self.qImageHalf = self.qImage.scaledToWidth(640);

        except:
            print("LNLSCamera - Except in scale and rotate!!!")
            return -1
        self.qImage = None

        self.qtPixMap = QtGui.QPixmap(self.qImageHalf)
        self.qImageHalf = None

        self.emit("imageReceived", self.qtPixMap)
        self.qtPixMap = None
        
        return 0

    def getStaticImage(self):
        qtPixMap = QtGui.QPixmap(self.source, "1")
        self.emit("imageReceived", qtPixMap)

    def getOneImage(self):
        self.imgArray = self.getValue(CAMERA_DATA)
        im_out = Image.fromarray(self.imgArray.astype('uint8')).convert('RGBA')
        buf = io.StringIO()
        im_out.save(buf,"JPEG")
        return buf

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
        return False

    def start_camera(self):
        self.setValue(CAMERA_BACK, 1)
        self.setValue(CAMERA_EN_BACK, 1)
        self.setValue(CAMERA_ACQ_STOP, 0)
        self.setValue(CAMERA_ACQ_START, 1)
        #
        #self.getCameraImage()
        #self.getStaticImage()
        #self.setLive(True)

    def stop_camera(self):
        self.setValue(CAMERA_ACQ_START, 0)
        self.setValue(CAMERA_ACQ_STOP, 1)

    def setLive(self, live):
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

    def imageType(self):
        return None

    def takeSnapshot(self, *args):
      jpeg_data=self.getOneImage()
      f = open(*(args + ("w",)))
      f.write("".join(map(chr, jpeg_data)))
      f.close()

    def __del__(self):
        print("LNLSCamera __del__")
        self.stop_camera()
        self.setLive(False)
