import logging
import webbrowser
from PyQt4 import QtCore, QtGui, uic
from configuration import conf
from pubsub import pub


class AboutWindow(QtGui.QDialog):

    main_window = None

    def __init__(self, main_window):
        super(AboutWindow, self).__init__()

        self.main_window = main_window
        self.logger = logging.getLogger(__name__)

        self.init_ui()

    def init_ui(self):
        self.logger.debug('Loading about window ui')
        self.ui = uic.loadUi('ui/about.ui', self)
        self.ui.setWindowTitle('Cender')
        self.ui.setWindowIcon(QtGui.QIcon('web.png'))

        self.ui.buttonBox.accepted.connect(self.ui.close)
        self.ui.btnRepo.clicked.connect(self.open_repo)

        self.ui.show()

    def open_repo(self):
        webbrowser.open('https://github.com/dougle/Cender')
