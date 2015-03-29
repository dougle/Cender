import logging
import time
import re
import os
import imp
import sys
from time import sleep
from PyQt4 import QtCore, QtGui, uic
from math import isnan
from configuration import conf
from pubsub import pub
from functools import partial

import os
import serial
from serial.tools import list_ports


class OptionsWindow(QtGui.QDialog):

    main_window = None
    config_item_prefix = 'config_item_'

    def __init__(self, main_window):
        super(OptionsWindow, self).__init__()

        self.main_window = main_window
        self.logger = logging.getLogger(__name__)

        self.init_ui()

    def init_ui(self):
        self.logger.debug('Loading options window ui')
        self.ui = uic.loadUi('ui/options.ui', self)
        self.ui.setWindowTitle('Cender')
        self.ui.setWindowIcon(QtGui.QIcon('web.png'))

        self.ui.buttonBox.accepted.connect(self.save_options)
        self.ui.buttonBox.rejected.connect(self.reject)
        self.ui.btnOpenPort.clicked.connect(self.test_connection)
        self.ui.btnSaveSettings.clicked.connect(
            partial(self.save_options_to_file, options_window=self.ui))
        self.ui.btnLoadSettings.clicked.connect(
            partial(self.load_options_from_file, options_window=self.ui))

        self.set_ui_from_conf()
        self.main_window.controller.add_tab_to_config(self.ui)

        self.ui.show()

    def set_ui_from_conf(self):
        # general tab
        self.ui.checkBoxEnableDebugLog.setChecked(
            conf.get('common.log_level') > 0)
        self.ui.checkBoxAddGcodeComments.setChecked(
            conf.get('common.add_gcode_comments_for_system_commands'))

        # connection tab

        self.ui.comboControllerBoard.setCurrentIndex(
            self.ui.comboControllerBoard.findText(
                conf.get('common.board_type')))
        self.ui.checkAutoConnect.setChecked(
            bool(conf.get('common.auto_connect')))

        # setup baud combo box
        for baud_rate in [
                '9600', '19200', '38400',
                '57600', '115200', '230400']:
            self.ui.comboBoxBaudRate.addItem(baud_rate)
        self.ui.comboBoxBaudRate.setCurrentIndex(
            self.ui.comboBoxBaudRate.findText(
                str(conf.get('connection.port.baud'))))

        # setup port combo box
        for port in self.fetch_ports():
            self.ui.cmbPort.addItem(port)
        self.ui.cmbPort.setCurrentIndex(
            self.ui.cmbPort.findText(conf.get('connection.port.name')))

        self.ui.radioImperial.setChecked(conf.get('common.units') == '0')
        self.ui.radioMetric.setChecked(conf.get('common.units') == '1')

        self.ui.radioSoft.setChecked(
            conf.get('connection.port.flow_control') == 'xonxoff')
        self.ui.radioHard.setChecked(
            conf.get('connection.port.flow_control') == 'rtscts')

        self.ui.comboBoxStopBits.setCurrentIndex(
            self.ui.comboBoxStopBits.findText(
                str(conf.get('connection.port.stopbits'))))
        self.ui.comboBoxParity.setCurrentIndex(
            self.ui.comboBoxParity.findText(
                str(conf.get('connection.port.parity'))))

        # interface

        self.ui.spinBoxLCDPrecision.setValue(
            float(conf.get('ui.lcd_precision')))

        self.ui.checkBoxShowVisualiser.setChecked(
            conf.get('ui.show_visualiser'))

        # clear
        for i in reversed(range(self.ui.offsetList.count())):
            if 'QHBoxLayout' in str(type(self.ui.offsetList.itemAt(i))):
                for j in reversed(range(self.ui.offsetList.itemAt(i).count())):
                    self.ui.offsetList.itemAt(i).itemAt(
                        j).widget().setParent(None)
                self.ui.offsetList.itemAt(i).setParent(None)

        # offsets
        for units, offset_name in enumerate(conf.get('ui.offset_names')):
            h_layout = QtGui.QHBoxLayout()

            remove_button = QtGui.QPushButton('-')
            remove_button.clicked.connect(
                partial(self.remove_offset, layout=h_layout))
            remove_button.setFixedWidth(20)
            h_layout.addWidget(remove_button)

            h_layout.addWidget(QtGui.QLineEdit(offset_name))
            self.ui.offsetList.insertLayout(
                (self.ui.offsetList.count() - 1), h_layout)

        self.ui.buttonAddOffset.clicked.connect(self.add_offset)
        self.reset_scroll_area(
            self.ui.offsetListScrollContents, self.ui.offsetList.count())

        self.ui.spinBoxLCDPrecision.setValue(
            float(conf.get('ui.lcd_precision')))

        self.ui.chkFilterFileCommands.setChecked(
            conf.get('common.filter_file_commands') == 'True')
        self.ui.checkBoxReducePrecForLongLines.setChecked(
            conf.get('common.restrict_file_precision') == 'True')

        # board config
        for key in sorted(self.main_window.controller.board_config):
            config_item = self.main_window.controller.board_config[key]

            h_layout = QtGui.QHBoxLayout()
            layout_geometry = h_layout.geometry()
            layout_geometry.setWidth(450)
            h_layout.setGeometry(layout_geometry)
            h_layout.setAlignment(QtCore.Qt.AlignLeft)

            label = QtGui.QLabel(config_item['id'])
            label.setFixedWidth(50)
            label.setAlignment(QtCore.Qt.AlignRight)
            h_layout.addWidget(label)

            label = QtGui.QLabel(' - ' + config_item['message'])
            label.setAlignment(QtCore.Qt.AlignLeft)
            label.setFixedWidth(300)
            h_layout.addWidget(label)

            line_edit = QtGui.QLineEdit(config_item['value'])
            line_edit.setFixedWidth(100)
            line_edit.setObjectName(
                self.config_item_prefix + config_item['id'])

            if 'units' in config_item and len(config_item['units']) > 0:
                line_edit.setToolTip(config_item['units'])

            h_layout.addWidget(line_edit)

            self.ui.configList.insertLayout(
                (self.ui.configList.count() - 1), h_layout)

        self.reset_scroll_area(
            self.ui.configListScrollContents, self.ui.configList.count())

    def save_options_to_file(self, options_window):
        self.set_options()

        filename = QtGui.QFileDialog.getSaveFileName(
            options_window, 'Choose Filename',
            conf.get('common.directory') + '/cender.config',
            'Config (*.config)')
        conf.save_to_file(filename)

    def load_options_from_file(self, options_window):
        filename = QtGui.QFileDialog.getOpenFileName(
            options_window, 'Choose Filename',
            conf.get('common.directory') + '/cender.config',
            'Config (*.config)')

        if len(filename):
            conf.load_from_file(filename)

            self.set_ui_from_conf()

            # setup main window after changes
            self.main_window.set_offsets()

    # resize the scroll content area
    def reset_scroll_area(self, scroll_area, count):
        scroll_geometry = scroll_area.geometry()
        scroll_geometry.setHeight(count * 31)
        scroll_area.setGeometry(scroll_geometry)

    def add_offset(self):
        index = (self.ui.offsetList.count() - 1)
        h_layout = QtGui.QHBoxLayout()

        remove_button = QtGui.QPushButton('-')
        remove_button.clicked.connect(
            partial(self.remove_offset, layout=h_layout))
        remove_button.setFixedWidth(20)
        h_layout.addWidget(remove_button)

        h_layout.addWidget(QtGui.QLineEdit('Work Offset ' + str(index + 1)))
        self.ui.offsetList.insertLayout(index, h_layout)

        self.reset_scroll_area(
            self.ui.offsetListScrollContents, self.ui.offsetList.count())

    def remove_offset(self, layout):
        self.logger.debug('Removing layout')
        if layout is not None and self.ui.offsetList.count() > 2:
            for i in reversed(range(layout.count())):
                layout.itemAt(i).widget().setParent(None)
            layout.setParent(None)

        self.reset_scroll_area(
            self.ui.offsetListScrollContents, self.ui.offsetList.count())

    def test_connection(self):
        listener = self.main_window.controller.listener_thread
        if listener is not None and listener.isRunning():
            listener.exit()

        board_type = str(self.ui.comboControllerBoard.currentText())
        driver_class_name = re.sub(r'[^a-zA-Z0-9]', '', board_type)
        driver_filename = re.sub(r'[^a-z0-9]+', '', board_type.lower())
        driver_directory = re.sub(r'[^a-z]+', '', driver_filename)

        sys.path.append(
            os.path.dirname(os.path.realpath(__file__)) + '/drivers/' +
            driver_directory)
        f, filename, description = imp.find_module(driver_filename)
        driver_module = imp.load_module(
            driver_class_name, f, filename, description)
        driver_class = getattr(driver_module, driver_class_name)

        controller = driver_class(self)

        flow_control = 'rtscts'
        if self.ui.radioSoft.isChecked():
            conf.set('connection.port.flow_control', 'xonxoff')

        parity = str(self.ui.comboBoxParity.currentText())
        parity = parity[0].upper()

        connection_message = 'Could not connect.'
        if controller.is_connected(
                str(self.ui.cmbPort.currentText()),
                int(self.ui.comboBoxBaudRate.currentText()),
                float(self.ui.comboBoxStopBits.currentText()),
                parity,
                flow_control):
            connection_message = 'Connected'
        QtGui.QMessageBox.information(
            self, driver_class_name + ' Connection', connection_message)

    def set_options(self):
        # general
        if self.ui.checkAutoConnect.isChecked():
            conf.set('common.log_level', 9)
        else:
            conf.set('common.log_level', 0)

        conf.set('common.add_gcode_comments_for_system_commands',
                 self.ui.checkBoxAddGcodeComments.isChecked())

        # connection tab
        conf.set(
            'common.board_type', self.ui.comboControllerBoard.currentText())
        board_id = re.sub(
            r' [\d\.]+$', '', str(conf.get('common.board_type')).lower())

        conf.set('connection.port.name', self.ui.cmbPort.currentText())
        conf.set('connection.port.baud', int(
            self.ui.comboBoxBaudRate.currentText()))

        conf.set('common.auto_connect', self.ui.checkAutoConnect.isChecked())

        if self.ui.radioImperial.isChecked():
            conf.set('common.units', 0)
        if self.ui.radioMetric.isChecked():
            conf.set('common.units', 1)

        if self.ui.radioSoft.isChecked():
            conf.set('connection.port.flow_control', 'xonxoff')
        if self.ui.radioHard.isChecked():
            conf.set('connection.port.flow_control', 'rtscts')

        conf.set(
            'connection.port.stopbits', self.ui.comboBoxStopBits.currentText())
        conf.set(
            'connection.port.parity', self.ui.comboBoxParity.currentText())

        # interface

        offsets = []
        for i in range(self.ui.offsetList.count()):
            leaf_object_type = str(type(
                self.ui.offsetList.itemAt(i).itemAt(1).widget()))
            if 'QHBoxLayout' in str(type(self.ui.offsetList.itemAt(i))) and \
                    'QLineEdit' in leaf_object_type:
                offset_text = self.ui.offsetList.itemAt(
                    i).itemAt(1).widget().text().replace(',', ' ')
                offsets.append(str(offset_text))

        conf.set('ui.offset_names', offsets)

        conf.set('ui.lcd_precision', int(self.ui.spinBoxLCDPrecision.value()))

        # filtering
        conf.set('common.filter_file_commands', str(
            self.ui.chkFilterFileCommands.isChecked()))
        conf.set('common.restrict_file_precision', str(
            self.ui.checkBoxReducePrecForLongLines.isChecked()))

        # board config
        for i in range(self.ui.configList.count()):
            if 'QHBoxLayout' in str(type(self.ui.configList.itemAt(i))):
                config_line_edit = self.ui.configList.itemAt(
                    i).itemAt(2).widget()

                if 'QLineEdit' in str(type(config_line_edit)):
                    config_id = str(
                        config_line_edit.objectName().replace(
                            self.config_item_prefix,
                            ''))
                    controller = self.main_window.controller
                    if controller.board_config[config_id]['value'] != \
                            config_line_edit.text():
                        if config_id in controller.board_config:
                            controller.send(
                                '$' + config_id + '=' +
                                str(config_line_edit.text()))

        self.main_window.controller.save_options(self.ui)

    def save_options(self):
        self.set_options()

        # setup main window after changes
        self.main_window.set_offsets()

        self.ui.close()

        return True

    def fetch_ports(self):
        ports = []
        if os.name == 'nt':
            # windows
            for i in range(256):
                try:
                    s = serial.Serial(i)
                    s.close()
                    ports.append('COM' + str(i + 1))
                except serial.SerialException:
                    pass
        else:
            # unix
            for port in list_ports.comports():
                ports.append(port[0])
        return ports
