import serial
import logging
import time
from configuration import conf
from controller_board import ControllerBoard


class Grbl(ControllerBoard):

    def __init__(self, main_window):
        super(Grbl, self).__init__()
        self.main_window = main_window

        self.logger = logging.getLogger(__name__)
        self.logger.debug('Grbl driver initialised')

    def connect(self):
        self.logger.debug('Connecting to Grbl')
