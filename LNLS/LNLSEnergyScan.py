"""
Descript. :
"""

import os
import math
import time
import gevent
import logging
import PyChooch

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from AbstractEnergyScan import AbstractEnergyScan
from HardwareRepository.TaskUtils import *
from HardwareRepository.BaseHardwareObjects import HardwareObject

from py4syn.epics.ScalerClass import Scaler
from py4syn.epics.SimCountableClass import SimCountable

class LNLSEnergyScan(AbstractEnergyScan, HardwareObject):
    # Common absorption edges by element and edge:
    ENERGY_EDGES = {    "Ac-K":0,"Ac-L1":19840,"Ac-L2":19083,"Ac-L3":15871,
                        "As-K":11867,"As-L1":0,"As-L2":0,"As-L3":0,
                        "At-K":0,"At-L1":17493,"At-L2":16785,"At-L3":14214,
                        "Au-K":0,"Au-L1":14353,"Au-L2":13734,"Au-L3":11919,
                        "Bi-K":0,"Bi-L1":16388,"Bi-L2":15711,"Bi-L3":13419,
                        "Br-K":13474,"Br-L1":0,"Br-L2":0,"Br-L3":0,
                        "Ce-K":0,"Ce-L1":6548,"Ce-L2":6164,"Ce-L3":0,
                        "Co-K":7709,"Co-L1":0,"Co-L2":0,"Co-L3":0,
                        "Cu-K":8979,"Cu-L1":0,"Cu-L2":0,"Cu-L3":0,
                        "Dy-K":0,"Dy-L1":9046,"Dy-L2":8581,"Dy-L3":7790,
                        "Er-K":0,"Er-L1":9751,"Er-L2":9264,"Er-L3":8358,
                        "Eu-K":0,"Eu-L1":8052,"Eu-L2":7617,"Eu-L3":6977,
                        "Fe-K":7112,"Fe-L1":0,"Fe-L2":0,"Fe-L3":0,
                        "Fr-K":0,"Fr-L1":18639,"Fr-L2":17907,"Fr-L3":15031,
                        "Ga-K":10367,"Ga-L1":0,"Ga-L2":0,"Ga-L3":0,
                        "Gd-K":0,"Gd-L1":8376,"Gd-L2":7930,"Gd-L3":7243,
                        "Ge-K":11103,"Ge-L1":0,"Ge-L2":0,"Ge-L3":0,
                        "Hf-K":0,"Hf-L1":11271,"Hf-L2":10739,"Hf-L3":9561,
                        "Hg-K":0,"Hg-L1":14839,"Hg-L2":14209,"Hg-L3":12284,
                        "Ho-K":0,"Ho-L1":9394,"Ho-L2":8918,"Ho-L3":8071,
                        "Ir-K":0,"Ir-L1":13419,"Ir-L2":12824,"Ir-L3":11215,
                        "Kr-K":14326,"Kr-L1":0,"Kr-L2":0,"Kr-L3":0,
                        "La-K":0,"La-L1":6266,"La-L2":0,"La-L3":0,
                        "Lu-K":0,"Lu-L1":10870,"Lu-L2":10349,"Lu-L3":9244,
                        "Mn-K":6539,"Mn-L1":0,"Mn-L2":0,"Mn-L3":0,
                        "Nb-K":18986,"Nb-L1":0,"Nb-L2":0,"Nb-L3":0,
                        "Nd-K":0,"Nd-L1":7126,"Nd-L2":6722,"Nd-L3":6208,
                        "Ni-K":8333,"Ni-L1":0,"Ni-L2":0,"Ni-L3":0,
                        "Os-K":0,"Os-L1":12968,"Os-L2":12385,"Os-L3":10871,
                        "Pa-K":0,"Pa-L1":0,"Pa-L2":0,"Pa-L3":16733,
                        "Pb-K":0,"Pb-L1":15861,"Pb-L2":15200,"Pb-L3":13035,
                        "Pm-K":0,"Pm-L1":7428,"Pm-L2":7013,"Pm-L3":6459,
                        "Po-K":0,"Po-L1":16939,"Po-L2":16244,"Po-L3":13814,
                        "Pr-K":0,"Pr-L1":6835,"Pr-L2":6440,"Pr-L3":0,
                        "Pt-K":0,"Pt-L1":13880,"Pt-L2":13273,"Pt-L3":11564,
                        "Ra-K":0,"Ra-L1":19237,"Ra-L2":18484,"Ra-L3":15444,
                        "Rb-K":15200,"Rb-L1":0,"Rb-L2":0,"Rb-L3":0,
                        "Re-K":0,"Re-L1":12527,"Re-L2":11959,"Re-L3":10535,
                        "Rn-K":0,"Rn-L1":18049,"Rn-L2":17337,"Rn-L3":14619,
                        "Se-K":12658,"Se-L1":0,"Se-L2":0,"Se-L3":0,
                        "Sm-K":0,"Sm-L1":7737,"Sm-L2":7312,"Sm-L3":6716,
                        "Sr-K":16105,"Sr-L1":0,"Sr-L2":0,"Sr-L3":0,
                        "Ta-K":0,"Ta-L1":11682,"Ta-L2":11136,"Ta-L3":9881,
                        "Tb-K":0,"Tb-L1":8708,"Tb-L2":8252,"Tb-L3":7514,
                        "Th-K":0,"Th-L1":0,"Th-L2":19693,"Th-L3":16300,
                        "Tl-K":0,"Tl-L1":15347,"Tl-L2":14698,"Tl-L3":12658,
                        "Tm-K":0,"Tm-L1":10116,"Tm-L2":9617,"Tm-L3":8648,
                        "U-K":0,"U-L1":0,"U-L2":0,"U-L3":17166,
                        "W-K":0,"W-L1":12100,"W-L2":11544,"W-L3":10207,
                        "Y-K":17038,"Y-L1":0,"Y-L2":0,"Y-L3":0,
                        "Yb-K":0,"Yb-L1":10486,"Yb-L2":9978,"Yb-L3":8944,
                        "Zn-K":9659,"Zn-L1":0,"Zn-L2":0,"Zn-L3":0,
                        "Zr-K":17998,"Zr-L1":0,"Zr-L2":0,"Zr-L3":0,"Cr-K":5989,"V-K":5465 }

    def __init__(self, name):
        AbstractEnergyScan.__init__(self)
        HardwareObject.__init__(self, name)
        self._tunable_bl = True

        self.can_scan = False
        self.ready_event = None
        self.scanning = False
        self.energy_motor = None
        self.archive_prefix = None
        self.thEdge = None
        self.scanData = None
        self.energy_scan_gen = None
        self.scaler = None
        
        self.db_connection_hwobj = None
        self.transmission_hwob = None
        self.beam_info_hwobj = None

    def init(self):
        """
        Descript. :
        """
        self.ready_event = gevent.event.Event()
        self.scanInfo = {}

        # ----------------------------------------------------------------------
        # Hardware objects
        self.beam_info_hwobj = self.getObjectByRole("beam_info")
        if self.beam_info_hwobj is None:
            logging.getLogger("HWR").warning('LNLSEnergyScan: Beam info hwobj not defined')

        self.energy_hwobj = self.getObjectByRole("energy")
        if self.energy_hwobj is None:
            logging.getLogger("HWR").warning('LNLSEnergyScan: Energy hwobj not defined')
        else:
            self.can_scan = True

        self.db_connection_hwobj = self.getObjectByRole("dbserver")
        if self.db_connection_hwobj is None:
            logging.getLogger("HWR").warning('LNLSEnergyScan: Database hwobj not defined')

        self.transmission_hwobj = self.getObjectByRole("transmission")
        if self.transmission_hwobj is None:
            logging.getLogger("HWR").warning('LNLSEnergyScan: Transmission hwobj not defined')

        # ----------------------------------------------------------------------
        # Py4Syn objects
        try:
            #self.scaler = Scaler(self.epics_scaler, int(self.epics_scaler_channel))   # REAL
            self.scaler = SimCountable(self.epics_scaler, self.epics_scaler_name)   # Simulated
        except:
            logging.getLogger("HWR").warning('LNLSEnergyScan: Error when instantiating a scaler')

         
    def scan_status_update(self, status):
        """
        Descript. :
        """
        if self.scanning:    
            if status == 'scanning':
                logging.getLogger("HWR").info('Executing energy scan...')
            elif status == 'ready':
                if self.scanning is True:
                    self.scanCommandFinished()
                    logging.getLogger("HWR").info('Energy scan finished')
            elif status == 'aborting':
                if self.scanning is True:
                    self.scanCommandAborted()
                    logging.getLogger("HWR").info('Energy scan aborted')    
            elif status == 'error':
                self.scanCommandFailed()      
                logging.getLogger("HWR").error('Energy scan failed')
            
    def emitNewDataPoint(self, values):
        """
        Descript. :
        """ 
        if len(values) > 0:
            try:
                x = values[0]
                y = values[1]

                if not (x == 0 and y == 0):
                    # if x is in keV, transform into eV otherwise let it like it is
                    # if point larger than previous point (for chooch)
                    if len(self.scanData) > 0: 
                        #print("x ::: ", x)
                        #print("self.scanData[-1][0] ::: ", self.scanData[-1][0])
                        if x > self.scanData[-1][0]:
                            self.scanData.append([(x < 1000 and round(float(x*1000.0), 2) or x), y])
                            #print("APPENDED ::: self.scanData[-1][0] ::: ", self.scanData[-1][0])
                    else:
                        self.scanData.append([(x < 1000 and round(float(x*1000.0), 2) or x), y])
                    self.emit('scanNewPoint', ((x < 1000 and round(float(x*1000.0), 2) or x), y, ))
            except:
                pass

    def isConnected(self):
        """
        Descript. :
        """
        return True

    def canScanEnergy(self):
        """
        Descript. :
        """
        return self.isConnected()

    def startEnergyScan(self, element, edge, directory, prefix, \
                 session_id = None, blsample_id = None, exptime = 2):
        """
        Descript. :
        """
        if not self.can_scan:
            logging.getLogger("HWR").error("EnergyScan: unable to start energy scan")
            self.scanCommandAborted() 
            return

        self.scanInfo = { "sessionId":  session_id, 
                          "blSampleId": blsample_id,
                          "element":    element,
                          "edgeEnergy": edge }
        self.scanData = []

        if not os.path.isdir(directory):
            logging.getLogger("HWR").debug("EnergyScan: creating directory %s" % directory)
            try:
                os.makedirs(directory)
            except OSError as diag:
                logging.getLogger("HWR").error("EnergyScan: error creating directory %s (%s)" % (directory, str(diag)))
                self.emit('energyScanStatusChanged', ("Error creating directory",))
                return False
        try:
            #if self.chan_scan_status.getValue() in ['ready', 'unknown', 'error']:    
            if (self.energy_hwobj.getState() == self.energy_hwobj.READY):
                if self.transmission_hwobj is not None:
                    self.scanInfo['transmissionFactor'] = self.transmission_hwobj.get_value()
                else:
                    self.scanInfo['transmissionFactor'] = None
                self.scanInfo['exposureTime'] = float(exptime)
                self.scanInfo['startEnergy'] = 0
                self.scanInfo['endEnergy'] = 0
                self.scanInfo['elementEdgeEnergy'] = None

                size_hor = None
                size_ver = None

                if self.beam_info_hwobj is not None:
                    size_hor, size_ver = self.beam_info_hwobj.get_beam_size()
                    size_hor = size_hor * 1000
                    size_ver = size_ver * 1000

                self.scanInfo['beamSizeHorizontal'] = size_hor
                self.scanInfo['beamSizeVertical'] = size_ver

                # self.chan_scan_start.setValue("%s;%s" % (element, edge))
                # -------------------------------------------------------------
                # Announce the scan started
                self.scanCommandStarted()
                # Call a procedure to perform the energy scan (in a different thread)
                self.energy_scan_gen = gevent.spawn(self.scanProcedure)
            else:
                logging.getLogger("HWR").error('Another energy scan in progress. Please wait when the scan is finished')
                self.emit('energyScanStatusChanged', ("Another energy scan in progress. Please wait when the scan is finished"))
                self.scanCommandFailed()
                return False
        except:
            logging.getLogger("HWR").error('EnergyScan: error in executing energy scan command')
            self.emit('energyScanStatusChanged', ("Error in executing energy scan command",))
            self.scanCommandFailed()
            return False
        return True

    def scanProcedure(self):
        # Combine element and edge
        elementEdge = '-'.join((self.scanInfo['element'], self.scanInfo['edgeEnergy']))
        elementEdgeEnergy = None

        # Announce we are scanning...
        self.scan_status_update("scanning")

        try:
            print("---------------------------------------------------------------------")
            print(" -:- ENERGY SCAN -:- ")
            print("---------------------------------------------------------------------")
            print("element; edge: ", self.scanInfo['element'], self.scanInfo['edgeEnergy'])
            elementEdgeEnergy = float(LNLSEnergyScan.ENERGY_EDGES[elementEdge])
            self.scanInfo['elementEdgeEnergy'] = elementEdgeEnergy
            print("energy: ", elementEdgeEnergy)
            print("---------------------------------------------------------------------")
            # Inform user
            logging.getLogger("user_level_log").info('Selected element, edge and energy on that edge: %s-%s, %.2f.' % (self.scanInfo['element'], self.scanInfo['edgeEnergy'], elementEdgeEnergy))
        except KeyError:
            logging.getLogger("user_level_log").error('Unknown energy for element-edge: %s.' % elementEdge)
            self.scanCommandFailed()
            return

        try:
            # Update start and end of energies to scan - this is because there are two different steps during scan
            # External limits (typical step of 1.0 eV)
            self.scanInfo['startEnergy'] = elementEdgeEnergy - float(self.external_energy_limits)
            self.scanInfo['endEnergy'] = elementEdgeEnergy + float(self.external_energy_limits)
            # Internal limits (typical step of 0.2 eV)
            self.scanInfo['startInternalLimit'] = elementEdgeEnergy - float(self.internal_energy_limits)
            self.scanInfo['endInternalLimit'] = elementEdgeEnergy + float(self.internal_energy_limits)
            print("Ranges: [ %f :: %f :: eV :: %f :: %f" % (self.scanInfo['startEnergy'], self.scanInfo['startInternalLimit'], self.scanInfo['endInternalLimit'], self.scanInfo['endEnergy']))
        except NameError:
            logging.getLogger("user_level_log").error('Missing necessary parameters in lnls-energy_scan.xml...')
            self.scanCommandFailed()
            return

        if (self.energy_hwobj):
            # Set start energy in KeV
            self.energy_hwobj.set_energy(round(float(self.scanInfo['startEnergy']) / 1000, 5))

            print("Data: %s | %s |" % (str("energy").ljust(8), str("intensity").ljust(12)))

            while(self.energy_hwobj.get_current_energy() <= (self.scanInfo['endEnergy'] / 1000)):
                # Configure and command scaler to count for specified time
                if (self.scaler):
                    self.scaler.setCountTime(self.scanInfo['exposureTime'])

                    #intensity = round(float(self.scaler.getIntensityCheck()), 5)   #REAL
                    self.scaler.startCount()    # Simulated
                    intensity = self.scaler.getValue()  # Simulated

                    # Plot the collected data
                    self.emitNewDataPoint((round(float(self.energy_hwobj.get_current_energy()) * 1000, 2), round(float(intensity),4)))
                    print("Data: %s | %s |" % (str(round(float(self.energy_hwobj.get_current_energy()) * 1000, 2)).ljust(8), str(intensity).ljust(12)))
                else:
                    logging.getLogger("user_level_log").error('No Scaler configured...')
                    self.scanCommandFailed()
                    break

                # Move to the next step
                if ((self.scanInfo['startInternalLimit'] / 1000) <= self.energy_hwobj.get_current_energy() <= (self.scanInfo['endInternalLimit'] / 1000)):
                    step = float(self.internal_step_scan)
                else:
                    step = float(self.external_step_scan)

                newEnergy = round(float(self.energy_hwobj.get_current_energy() + (step / 1000)), 5)
                # Move to new energy
                self.energy_hwobj.set_energy(newEnergy)

            # Announce we finished!
            self.scan_status_update("ready")

        else:
            logging.getLogger("user_level_log").error('No Energy hardware object configured...')
            self.scanCommandFailed()
            return

    def cancelEnergyScan(self, *args):
        """
        Descript. :
        """
        if self.scanning:
            # self.cmd_scan_abort()
            # Abort the thread that is processing energy scan...
            self.energy_scan_gen.kill()
            # Call procedure to finish the current scan
            self.scanCommandAborted()

    def scanCommandStarted(self, *args):
        """
        Descript. :
        """
        title = "%s %s: %s %s" % (self.scanInfo["sessionId"], 
            self.scanInfo["blSampleId"], self.scanInfo["element"], self.scanInfo["edgeEnergy"])
        dic = {'xlabel': 'energy', 'ylabel': 'counts', 'scaletype': 'normal', 'title': title}
        self.scanInfo['startTime'] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.scanning = True
        self.emit('energyScanStarted', ())

    def scanCommandFailed(self, *args):
        """
        Descript. :
        """
        self.scanInfo['endTime'] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.scanning = False
        self.store_energy_scan()
        self.emit('energyScanFailed', ())
        self.ready_event.set()

    def scanCommandAborted(self, *args):
        """
        Descript. :
        """
        self.scanning = False
        # Stop the energy modification, movement of monochromator
        self.energy_hwobj.stop()
        # Emit a signal to inform user
        self.emit('energyScanFailed', ())
        self.ready_event.set()

    def scanCommandFinished(self, *args):
        """
        Descript. :
        """
        with cleanup(self.ready_event.set):
            self.scanInfo['endTime'] = time.strftime("%Y-%m-%d %H:%M:%S")
            logging.getLogger("HWR").debug("LNLSEnergyScan: energy scan finished")
            self.scanning = False
            self.scanInfo["startEnergy"] = self.scanData[-1][0]
            self.scanInfo["endEnergy"] = self.scanData[-1][1]
            self.emit('energyScanFinished', (self.scanInfo,))

    def doChooch(self, elt, edge, scan_directory, archive_directory, prefix):
        """
        Descript. :
        """
        symbol = "_".join((elt, edge))
        scan_file_prefix = os.path.join(scan_directory, prefix) 
        archive_file_prefix = os.path.join(archive_directory, prefix)

        if os.path.exists(scan_file_prefix + ".raw"):
            i = 1
            while os.path.exists(scan_file_prefix + "%d.raw" %i):
                  i = i + 1
            scan_file_prefix += "_%d" % i
            archive_file_prefix += "_%d" % i
       
        scan_file_raw_filename = os.path.extsep.join((scan_file_prefix, "raw"))
        print("scan_file_raw_filename: ", scan_file_raw_filename)
        #archive_file_raw_filename = os.path.extsep.join((archive_file_prefix, "raw"))
        #print("archive_file_raw_filename: ", archive_file_raw_filename)
        scan_file_efs_filename = os.path.extsep.join((scan_file_prefix, "efs"))
        print("scan_file_efs_filename: ", scan_file_efs_filename)
        #archive_file_efs_filename = os.path.extsep.join((archive_file_prefix, "efs"))
        #print("archive_file_efs_filename: ", archive_file_efs_filename)
        scan_file_png_filename = os.path.extsep.join((scan_file_prefix, "png"))
        print("scan_file_png_filename: ", scan_file_png_filename)
        #archive_file_png_filename = os.path.extsep.join((archive_file_prefix, "png"))
        #print("archive_file_png_filename: ", archive_file_png_filename)

        try:
            if not os.path.exists(scan_directory):
                os.makedirs(scan_directory)
            if not os.path.exists(archive_directory):
                os.makedirs(archive_directory)
        except:
            logging.getLogger("HWR").exception("LNLSEnergyScan: could not create energy scan result directory.")
            self.store_energy_scan()
            self.emit("energyScanFailed", ())
            return

        try:
            scan_file_raw = open(scan_file_raw_filename, "w")
            #archive_file_raw = open(archive_file_raw_filename, "w")
        except:
            logging.getLogger("HWR").exception("LNLSEnergyScan: could not create energy scan result raw file")
            self.store_energy_scan()
            self.emit("energyScanFailed", ())
            return
        else:
            #print("----------------------------------------------------------------")
            scanData = []
            #print("len(self.scanData): ", len(self.scanData))
            #print("----------------------------------------------------------------")
            #print("self.scanData")
            for i in range(len(self.scanData)):
                x = round(float(self.scanData[i][0]), 2)
                #print("data x: ", x)
                x = x < 1000 and round(float(x * 1000.0), 2) or x 
                #print("data x after: ", x)
                y = round(float(self.scanData[i][1]), 4)
                #print("data y: ", y)
                scanData.append((x, y))
                scan_file_raw.write("%.2f, %.4f\r\n" % (x, y))
                #archive_file_raw.write("%f,%f\r\n" % (x, y)) 
            scan_file_raw.close()
            #archive_file_raw.close()
            self.scanInfo["scanFileFullPath"] = str(scan_file_raw_filename)
            #print("----------------------------------------------------------------")

        pk, fppPeak, fpPeak, ip, fppInfl, fpInfl, chooch_graph_data = \
             PyChooch.calc(scanData, elt, edge, scan_file_efs_filename)

        rm = (pk + 30) / 1000.0
        pk = pk / 1000.0
        savpk = pk
        ip = ip / 1000.0
        comm = ""

        #IK TODO clear this
        #self.scanInfo['edgeEnergy'] = 0.1
        #self.thEdge = self.scanInfo['edgeEnergy']
        # LNLS
        if (self.scanInfo['elementEdgeEnergy'] is None):
            self.scanInfo['elementEdgeEnergy'] = 0.1
        self.thEdge = round(float(self.scanInfo['elementEdgeEnergy'] / 1000), 5)

        logging.getLogger("HWR").info("th. Edge %s ; chooch results are pk=%f, ip=%f, rm=%f" % (self.thEdge, pk,ip,rm))

        #should be better, but OK for time being
        self.thEdgeThreshold = 0.02
        if math.fabs(self.thEdge - ip) > self.thEdgeThreshold:
          pk = 0
          ip = 0
          rm = self.thEdge + 0.03
          comm = 'Calculated peak (%f) is more that 20eV away from the theoretical value (%f). Please check your scan' % \
                 (savpk, self.thEdge)

          logging.getLogger("HWR").warning('EnergyScan: calculated peak (%f) is more that 20eV %s the theoretical value (%f). Please check your scan and choose the energies manually' % \
                   (savpk, (self.thEdge - ip) > 0.02 and "below" or "above", self.thEdge))

        # LNLS
        # try:
        #     fi = open(scan_file_efs_filename)
        #     fo = open(archive_file_efs_filename, "w")
        # except:
        #     self.store_energy_scan()
        #     self.emit("energyScanFailed", ())
        #     return
        # else:
        #     fo.write(fi.read())
        #     fi.close()
        #     fo.close()

        self.scanInfo["peakEnergy"] = pk
        self.scanInfo["inflectionEnergy"] = ip
        self.scanInfo["remoteEnergy"] = rm
        self.scanInfo["peakFPrime"] = fpPeak
        self.scanInfo["peakFDoublePrime"] = fppPeak
        self.scanInfo["inflectionFPrime"] = fpInfl
        self.scanInfo["inflectionFDoublePrime"] = fppInfl
        self.scanInfo["comments"] = comm

        # Moving to Peak
        logging.getLogger("user_level_log").info("Moving to peack of energy: %.3f." % (pk))
        self.energy_hwobj.set_energy(pk)

        chooch_graph_x, chooch_graph_y1, chooch_graph_y2 = list(zip(*chooch_graph_data))
        chooch_graph_x = list(chooch_graph_x)
        for i in range(len(chooch_graph_x)):
            chooch_graph_x[i] = chooch_graph_x[i] / 1000.0

        #logging.getLogger("HWR").info("LNLSEnergyScan: Saving png" )
        # prepare to save png files
        title = "%s  %s  %s\n%.4f  %.2f  %.2f\n%.4f  %.2f  %.2f" % \
              ("energy", "f'", "f''", pk, fpPeak, fppPeak, ip, fpInfl, fppInfl) 
        fig = Figure(figsize = (15, 11))
        ax = fig.add_subplot(211)
        ax.set_title("%s\n%s" % (scan_file_efs_filename, title))
        ax.grid(True)
        ax.plot(*(list(zip(*scanData))), **{"color": 'black'})
        ax.set_xlabel("Energy")
        ax.set_ylabel("MCA counts")
        ax2 = fig.add_subplot(212)
        ax2.grid(True)
        ax2.set_xlabel("Energy")
        ax2.set_ylabel("")
        handles = []
        handles.append(ax2.plot(chooch_graph_x, chooch_graph_y1, color = 'blue'))
        handles.append(ax2.plot(chooch_graph_x, chooch_graph_y2, color = 'red'))
        canvas = FigureCanvasAgg(fig)

        #self.scanInfo["jpegChoochFileFullPath"] = str(archive_file_png_filename)
        try:
            logging.getLogger("HWR").info("Rendering energy scan and Chooch graphs to PNG file : %s", scan_file_png_filename)
            canvas.print_figure(scan_file_png_filename, dpi = 80)
        except:
            logging.getLogger("HWR").exception("could not print figure")

        # try:
        #     logging.getLogger("HWR").info("Saving energy scan to archive directory for ISPyB : %s", archive_file_png_filename)
        #     canvas.print_figure(archive_file_png_filename, dpi = 80)
        # except:
        #     logging.getLogger("HWR").exception("could not save figure")

        self.store_energy_scan()

        logging.getLogger("HWR").info("<chooch> returning" )
        self.emit('choochFinished', (pk, fppPeak, fpPeak, ip, fppInfl, fpInfl, 
                 rm, chooch_graph_x, chooch_graph_y1, chooch_graph_y2, title))
        return pk, fppPeak, fpPeak, ip, fppInfl, fpInfl, rm, chooch_graph_x, \
                 chooch_graph_y1, chooch_graph_y2, title

    def scanStatusChanged(self, status):
        """
        Descript. :
        """
        self.emit('energyScanStatusChanged', (status,))

    def updateEnergyScan(self, scan_id, jpeg_scan_filename):
        """
        Descript. :
        """
        pass

    def getElements(self):
        """
        Descript. :
        """
        elements = []
        try:
            for el in self["elements"]:
                elements.append({"symbol":el.symbol, "energy":el.energy})
        except IndexError:
            pass
        return elements

    # Mad energies commands
    def getDefaultMadEnergies(self):
        """
        Descript. :
        """
        energies = []
        try:
            for el in self["mad"]:
                energies.append([float(el.energy), el.directory])
        except IndexError:
            pass
        return energies

    def get_scan_data(self):
        """
        Descript. : returns energy scan data.
                    List contains tuples of (energy, counts)
        """
        return self.scanData 

    def store_energy_scan(self):
        """
        Descript. :
        """
        blsampleid = self.scanInfo['blSampleId']
        self.scanInfo.pop('blSampleId')
        if self.db_connection_hwobj:
            db_status = self.db_connection_hwobj.storeEnergyScan(self.scanInfo)
            if blsampleid is not None:
                try:
                    energyscanid = int(db_status['energyScanId'])
                except:
                    pass
                else:
                    asoc = {'blSampleId':blsampleid, 'energyScanId': energyscanid}
                    self.db_connection_hwobj.associateBLSampleAndEnergyScan(asoc)
