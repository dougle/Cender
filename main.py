#!/usr/bin/python

import sys
import logging
import os.path
from PyQt4 import QtCore, QtGui, uic
from configuration import conf

from main_window import MainWindow


def main():
    app_name = 'Cender'
    log_filename = app_name.lower() + '.log'
    logging.basicConfig(filename=log_filename, level=logging.DEBUG)

    logger = logging.getLogger(app_name.lower())
    logger.debug('Logging initialised')

    app = QtGui.QApplication(sys.argv)
    logger.debug('Application initialised')

    conf.set('ui.app.author', "Dougle")

    main_window = MainWindow()

    sys.exit(app.exec_())


def trace(frame, event, arg):
    with open('trace.log', 'a') as trace_file:
        trace_file.write("%s, %s:%d\n" %
                         (event, frame.f_code.co_filename, frame.f_lineno))
    return trace

if __name__ == '__main__':
    # sys.settrace(trace)
    main()
