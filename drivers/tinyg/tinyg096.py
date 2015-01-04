import logging
import re
from configuration import conf
from tinyg import TinyG
from pubsub import pub


class TinyG096(TinyG):

    """
      0.96 is the lowest supported version and the default so
      all code is in the parent class
    """

    def __init__(self, main_window):
        super(TinyG096, self).__init__(main_window)
