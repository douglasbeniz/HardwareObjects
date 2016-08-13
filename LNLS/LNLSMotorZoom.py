"""
LNLSMotorZoom
"""

from LNLSMotor import LNLSMotor


#------------------------------------------------------------------------------
# Zoom position array
ZOOM_MOTOR_POSITION = [0, 286, 410, 492, 565, 626, 676]

#------------------------------------------------------------------------------
class LNLSMotorZoom(LNLSMotor):
    def __init__(self, name):
        LNLSMotor.__init__(self, name)

    def init(self):
        LNLSMotor.init(self)

        self._last_position_name = None

        self.predefinedPositions = { "Zoom 0.5": 0, "Zoom 1": 1, "Zoom 1.5": 2, "Zoom 2": 3, "Zoom 2.5": 4, "Zoom 3": 5, "Zoom 3.5": 6}
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

    def positionChanged(self, value):
        if (round(value) in ZOOM_MOTOR_POSITION):
            positionName = self.getCurrentPositionName(round(value))
            if self._last_position_name != positionName:
                self._last_position_name = positionName
                self.emit('predefinedPositionChanged', (positionName, positionName and value or None, ))
