from HardwareRepository.BaseHardwareObjects import Device
from py4syn.epics.AmptekMCAClass import AmptekMCA

import logging
import gevent

# SHUTTER = 'safetyShutter'

OPEN  = 1
CLOSE = 0

class LNLSMcaControl(Device):
    mcaState = {
        0: 'unknown',
        3: 'closed',
        4: 'opened',
        9: 'moving',
        17: 'automatic',
        23: 'fault',
        46: 'disabled',
        -1: 'error'
        }
  
    def __init__(self, name):
        Device.__init__(self, name)

        self.mcaStateValue = 3

    def init(self):
        self.setIsReady(False)

        # Thread to show dead-time values...
        self.dead_time_gen = None

        # Do not start it at beginning...
        #self.connectMca()
        self.mca = None

        self._monitor = False


    def connectMca(self):
        try:
            # Update state
            self.mcaStateValue = 4
            # Emit signal
            self.emit('shutterStateChanged', (LNLSMcaControl.mcaState[self.mcaStateValue], 'wait...',))

            # Create a new instance
            self.mca = AmptekMCA(mca_ip=self.mcaIPAddress, udp_port=self.mcaUdpPort)

            # Wait a while to stablish connection
            gevent.sleep(3)

            # Update state
            self.mcaStateValue = 4
            # Emit signal
            self.emit('shutterStateChanged', (LNLSMcaControl.mcaState[self.mcaStateValue], str(self.mca.getStatus()),))
        except:
            logging.getLogger("HWR").error('Error when instantiating Amptek MCA... Is it connected?')
            self.mca = None


    def disconnectMca(self):
        try:
            if (self.mca):
                self.mca.closeConnection()
        except:
            logging.getLogger("HWR").error('Error when closing Amptek MCA...')

        # Reset object        
        self.mca = None


    def valueChanged(self, value):
        self.mcaStateValue = (4 if (value == OPEN) else 3)
        self.emit('shutterStateChanged', (LNLSMcaControl.mcaState[self.mcaStateValue], LNLSMcaControl.mcaState[self.mcaStateValue],))

       
    def getShutterState(self):
        return LNLSMcaControl.mcaState[self.mcaStateValue] 


    def shutterIsOpen(self):
        return (self.mcaStateValue == OPEN)


    def enableControls(self, enable=True):
        self.emit('enableControls', enable)


    def isShutterOk(self):
        return True

    def monitorDeadTime(self):
        self._monitor = True

        while self._monitor:
            try:
                #print("Dead-time: ", self.mca.getDeadTime())
                # Update state
                self.mcaStateValue = 4
                # Emit signal
                self.emit('shutterStateChanged', (LNLSMcaControl.mcaState[self.mcaStateValue], str('Dead-time: ') + str(self.mca.getDeadTime()),))
            except:
                self._monitor = False
                pass

    def openShutter(self):
        # Update shutter
        if (not self.mca):
            self.connectMca()

        try:
            if (self.mca):
                # Update state
                self.mcaStateValue = 4
                # Emit signal
                self.emit('shutterStateChanged', (LNLSMcaControl.mcaState[self.mcaStateValue], str(self.mca.getStatus()),))
                # Wait a while to give time to user see the status...
                gevent.sleep(2)
            else:
                # Update state
                self.mcaStateValue = 3
                # Emit signal
                self.emit('shutterStateChanged', (LNLSMcaControl.mcaState[self.mcaStateValue], LNLSMcaControl.mcaState[self.mcaStateValue],))
        except:
            logging.getLogger("HWR").error('Error when opening Amptek MCA...')
            # Update state
            self.mcaStateValue = 3
            # Emit signal
            self.emit('shutterStateChanged', (LNLSMcaControl.mcaState[self.mcaStateValue], LNLSMcaControl.mcaState[self.mcaStateValue],))

        if (not self.dead_time_gen):
            self.dead_time_gen = gevent.spawn(self.monitorDeadTime)


    def stopMonitorDeadtime(self):
        if (self.dead_time_gen):
            self._monitor = False
            self.dead_time_gen.kill()
            gevent.sleep(1)
            self.dead_time_gen = None


    def closeShutter(self):
        #
        self.stopMonitorDeadtime()

        # Update shutter
        self.disconnectMca()

        # Update state
        self.mcaStateValue = 3
        self.emit('shutterStateChanged', (LNLSMcaControl.mcaState[self.mcaStateValue], "disconnected",))


    def __del__(self):
        print("LNLSMcaControl __del__")

        #
        self.stopMonitorDeadtime()
        #
        self.disconnectMca()
