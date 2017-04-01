"""
LNLSMotorZoom
"""

from LNLSMotor import LNLSMotor

#------------------------------------------------------------------------------
# Zoom position array
ZOOM_MOTOR_POSITION = [0, 286, 400, 410, 492, 565, 626, 676]

#PIXELS_PER_MM = [[x],[y]]
#PIXELS_PER_MM = [[85.0, 202.4, 300.1, 307.6, 404.8, 510.1, 607.3, 720.2], [85.0, 202.4, 300.1, 307.6, 404.8, 510.1, 607.3, 720.2]]
# Only the PIXELS_PER_MM[[2],[2]] is calibrated! :: [[456], [455]]
#PIXELS_PER_MM = [[129.2, 307.5, 456, 467.4, 615.1, 775.1, 922.8, 1094.3], [128.9, 306.9, 455, 466.4, 613.7, 773.4, 920.8, 1091.9]]

#------------------------------------------------------------------------------
# Calibration by alexandre.santos@lnls.br at 06-Mar-2017
#------------------------------------------------------------------------------
# Zoom      um  
# 0.5       5.95    1 pixel
# 1.0       2.35    1 pixel
# 1.5       1.59    1 pixel
# 2.0       1.18    1 pixel
# 2.5       0.95    1 pixel
# 3.0       0.80    1 pixel
# 3.5       0.75    1 pixel

#------------------------------------------------------------------------------
# Calculation (for Pixels x mm)
#------------------------------------------------------------------------------
# 1 / (5.95 * 10E-4)    =      168.1
# 1 / (2.35 * 10E-4)    =      425.5
# 1 / (1.59 * 10E-4)    =      628.9
# 1 / (1.18 * 10E-4)    =      847.5
# 1 / (0.95 * 10E-4)    =     1052.6
# 1 / (0.80 * 10E-4)    =     1250.0
# 1 / (0.75 * 10E-4)    =     1333.3
PIXELS_PER_MM = [[168.1, 425.5, 500, 628.9, 847.5, 1052.6, 1250.0, 1333.3], [168.1, 425.5, 500, 628.9, 847.5, 1052.6, 1250.0, 1333.3]]

#------------------------------------------------------------------------------
class LNLSMotorZoom(LNLSMotor):
    def __init__(self, name):
        LNLSMotor.__init__(self, name)

    def init(self):
        LNLSMotor.init(self)

        self._last_position_name = None

        self.predefinedPositions = { "Zoom 0.5": 0, "Zoom 1": 1, "Zoom 1.5": 3, "Zoom 2": 4, "Zoom 2.5": 5, "Zoom 3": 6, "Zoom 3.5": 7 }
        #self.predefinedPositions = { "Zoom 0.5": 0, "Zoom 1": 1, "Zoom 1.46": 2, "Zoom 1.5": 3, "Zoom 2": 4, "Zoom 2.5": 5, "Zoom 3": 6, "Zoom 3.5": 7 }
        #self.predefinedPositions = { "Zoom 1.46": 2 }
        self.sortPredefinedPositionsList()

    def sortPredefinedPositionsList(self):
        self.predefinedPositionsNamesList = list(self.predefinedPositions.keys())
        self.predefinedPositionsNamesList.sort()

    def getPredefinedPositionsList(self):
        return self.predefinedPositionsNamesList

    def moveToPosition(self, zoomPosition):
        LNLSMotor.move(self, ZOOM_MOTOR_POSITION[self.predefinedPositions[zoomPosition]])

    def getCurrentPositionName(self, position=None):
        if (not position):
            position = round(self.getPosition())

        try:
            # Return the key of predefinedPositions based on the value which is obtained by the index of ZOOM_MOTOR_POSITION array
            predefPosition = list(self.predefinedPositions.keys())[list(self.predefinedPositions.values()).index(ZOOM_MOTOR_POSITION.index(position))]
            return(predefPosition)
        except:
            return ""
            pass

    # -------------------------------------------------------------------------
    # index 0 = X
    # index 1 = Y
    # -------------------------------------------------------------------------
    def getPixelsPerMm(self, index, position=None):
        if (not position):
            position = round(self.getPosition())

        try:
            # Return the key of predefinedPositions based on the value which is obtained by the index of ZOOM_MOTOR_POSITION array
            pixelsPerMn = PIXELS_PER_MM[index][ZOOM_MOTOR_POSITION.index(position)]
            return(pixelsPerMn)
        except:
            return 0
            pass

    def positionChanged(self, value):
        if (round(value) in ZOOM_MOTOR_POSITION):
            positionName = self.getCurrentPositionName(round(value))
            if self._last_position_name != positionName:
                self._last_position_name = positionName
                self.emit('predefinedPositionChanged', (positionName, positionName and value or None, ))
