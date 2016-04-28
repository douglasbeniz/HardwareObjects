"""Class for cameras connected to framegrabbers run by Taco Device Servers
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
from PyQt4 import QtGui
import io

#-----------------------------------------------------------------------------
ALLIED_DATA      = "epicsAllied_data"
ALLIED_BACK      = "epicsAllied_back"
ALLIED_EN_BACK   = "epicsAllied_en_back"
ALLIED_ACQ       = "epicsAllied_acq"
ALLIED_ACQ_START = "epicsAllied_acq_start"
ALLIED_ACQ_STOP  = "epicsAllied_acq_stop"

#-----------------------------------------------------------------------------
class LNLSCamera(BaseHardwareObjects.Device):

    def __init__(self,name):
        BaseHardwareObjects.Device.__init__(self,name)
        self.liveState = False

    def _init(self):
        self.setIsReady(True)

    def init(self):
        self.imagegen = None

    def imageGenerator(self, delay):
        while True: 
            self.getCameraImage()
            time.sleep(delay)

    def getCameraImage(self):
        imgArray = self.getValue(ALLIED_DATA)
        imageArray = numpy.array(imgArray)
        imageArray = imageArray.reshape((1038,1388))

        image = Image.fromarray(imageArray)
        newImage = image.resize((519, 694), Image.ANTIALIAS)

        qtImage = ImageQt(newImage)
        qtPixMap = QtGui.QPixmap.fromImage(qtImage)

        self.emit("imageReceived", qtPixMap)

    def getStaticImage(self):
        qtPixMap = QtGui.QPixmap(self.source, "1")

        self.emit("imageReceived", qtPixMap)

    def getOneImage(self):

        a = numpy.random.rand(485,650) * 255
        im_out = Image.fromarray(a.astype('uint8')).convert('RGBA')
        buf = io.StringIO()
        im_out.save(buf,"JPEG")
        return buf

    def get_image_dimensions(self):
        return (519*694)

    def contrastExists(self):
        return False

    def brightnessExists(self):
        return False

    def gainExists(self):
        return False

    def start_camera(self):
        self.setValue(ALLIED_BACK, 1)
        self.setValue(ALLIED_EN_BACK, 1)
        self.setValue(ALLIED_ACQ_STOP, 0)
        self.setValue(ALLIED_ACQ_START, 1)
        self.setValue(ALLIED_ACQ, 1)
        #
        print("start_camera......")
        #self.getCameraImage()
        #self.getStaticImage()
        self.setLive(True)

    def stop_camera(self):
        self.setValue(ALLIED_ACQ, 0)
        self.setValue(ALLIED_ACQ_START, 0)
        self.setValue(ALLIED_ACQ_STOP, 1)

    def setLive(self, live):
        print("Setting camera live ", live)
        if live and self.liveState == live:
            return
        
        if live:
            self.imagegen = gevent.spawn(self.imageGenerator,  (self.getProperty("interval") or 500)/1000.0 )
            self.liveState = live
        else:
            self.imagegen.kill()
            self.liveState = live
            self.stop_camera()
        return True

    def imageType(self):
        return None

    def takeSnapshot(self, *args):
      jpeg_data=self.getOneImage()
      f = open(*(args + ("w",)))
      f.write("".join(map(chr, jpeg_data)))
      f.close()       
