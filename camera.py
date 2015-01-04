import cv2
import logging
import time
from PyQt4 import QtCore, QtGui, uic


class Camera(QtCore.QThread):
    device = None
    frameWidget = None
    # new_frame = QtCore.pyqtSignal(QtGui.QPixmap)

    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        # super(Camera, self).__init__()
        self.logger = logging.getLogger(__name__)

        self.logger.debug('Set up camera thread')
        self.device = cv2.VideoCapture(0)
        # self.camera_frame = camera_frame

    def play(self):
        self.logger.debug('Set up camera timer')
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.show_frame)
        self._timer.start(400)

    def stop(self):
        self._timer.stop()

    def run(self):
        self.play()
        self.exec_()

    def timer_timeout(self):
        self.logger.debug('timeout')

    def show_frame(self):
        try:
            if self.frameWidget is not None:
                self.logger.debug(
                    str(round(time.time() * 1000)) + ' fetching camera frame')
                frame = self.convertFrame(self.capture_next_frame())
                self.frameWidget.setPixmap(frame)
                self.frameWidget.setScaledContents(True)

            # self.new_frame.emit(frame)
        except TypeError:
            self.logger.debug('Error fetching frame')
            pass

    def capture_next_frame(self):
        """
        capture frame and reverse RBG BGR and return opencv image
        """
        self.logger.debug(
            str(round(time.time() * 1000)) + ' fetching new camera frame')
        ret, readFrame = self.device.read()
        if ret:
            return cv2.cvtColor(readFrame, cv2.COLOR_BGR2RGB)
        return None

    def convertFrame(self, frame):
        """
        converts frame to format suitable for QtGui
        """
        if frame is None:
            return None

        try:
            height, width = frame.shape[:2]
            img = QtGui.QImage(frame,
                               width,
                               height,
                               QtGui.QImage.Format_RGB888)
            img = QtGui.QPixmap.fromImage(img)
            return img
        except:
            return None
