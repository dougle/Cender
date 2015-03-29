import logging
import time
import re
import os
import imp
import sys
from time import sleep
from PyQt4 import QtCore, QtGui, uic
from math import isnan, floor, sqrt
from configuration import conf
from camera import Camera
from pubsub import pub
from functools import partial
from options_window import OptionsWindow
from about_window import AboutWindow

from visualisation import VisualisationWidget, Visualiser

import struct


class MainWindow(QtGui.QMainWindow):

    camera_thread = None
    current_offset_index = 0
    controller = None

    def __init__(self):
        super(MainWindow, self).__init__()

        self.logger = logging.getLogger(__name__)

        driver_class_name = re.sub(
            r'[^a-zA-Z0-9]', '', conf.get('common.board_type'))
        driver_filename = re.sub(
            r'[^a-z0-9]+', '', conf.get('common.board_type').lower())
        driver_directory = re.sub(r'[^a-z]+', '', driver_filename)

        sys.path.append(
            os.path.dirname(os.path.realpath(__file__)) + '/drivers/' +
            driver_directory)
        f, filename, description = imp.find_module(driver_filename)
        driver_module = imp.load_module(
            driver_class_name, f, filename, description)
        driver_class = getattr(driver_module, driver_class_name)

        self.init_ui()

        self.controller = driver_class(self)
        self.logger.debug(driver_class_name + ' driver loaded from ' +
                          'drivers/' + driver_directory + '/' +
                          driver_filename)

        self.logger.debug('Setting up controller to gui events')
        pub.subscribe(self.position_received_handler, 'position-received')
        pub.subscribe(self.velocity_received_handler, 'velocity-received')
        pub.subscribe(self.axis_received_handler, 'axis-received')
        pub.subscribe(self.home_received_handler, 'home-received')
        pub.subscribe(self.line_received_handler, 'line-received')
        pub.subscribe(self.line_sent_handler, 'line-sent')
        pub.subscribe(self.error_received_handler, 'error-received')
        pub.subscribe(self.feed_rate_sent_handler, 'feed-rate-sent')
        pub.subscribe(self.reset_received_handler, 'reset-received')
        pub.subscribe(self.units_received_handler, 'units-received')
        pub.subscribe(self.dist_mode_received_handler, 'dist-mode-received')
        pub.subscribe(self.connect_received_handler, 'connect-received')
        pub.subscribe(self.config_changed_handler, 'config-changed')
        pub.subscribe(self.config_fetched_handler, 'config-fetched')
        pub.subscribe(self.disconnect_received_handler, 'disconnect-received')
        pub.subscribe(self.programme_progress_handler, 'programme-progress')
        pub.subscribe(self.queue_size_handler, 'queue-size')
        pub.subscribe(self.start_of_file_handler, 'start-of-file')
        pub.subscribe(self.end_of_file_handler, 'end-of-file')
        pub.subscribe(self.timer_tick_handler, 'timer-tick')
        pub.subscribe(self.idle_handler, 'idle')
        pub.subscribe(self.busy_handler, 'busy')

        if bool(conf.get('common.auto_connect')):
            self.btn_connect_clicked()

    # 1 disconnected
    # 2 fetching config
    # 3 connected
    def comm_state(self, state):
        self.logger.debug('comm state ' + str(state))
        self.toggle_all_ui_elements(bool(state >= 3))
        self.logger.debug(
            'Switching buttons: ' + str(state) + ' ' + str(bool(state == 1)))
        self.ui.btnConnect.setVisible(bool(state < 2))
        self.ui.btnDisconnect.setVisible(bool(state > 1))
        if self.controller is not None:
            self.ui.btnFindHome.setEnabled(
                bool(len(self.controller.installed_homes) > 0 and state >= 3))

    # event handlers
    def connect_received_handler(self):
        self.logger.debug('controller Connected signal received')
        self.set_comm_status('Fetching Config')
        self.comm_state(2)

    def restore_last_positions(self):
        for axis_letter in self.controller.installed_axis:
            if conf.get('last_positions.' + axis_letter.lower()) is not None:
                self.controller.reset_axis(
                    axis_letter.upper(),
                    conf.get('last_positions.' + axis_letter.lower()))

    def config_changed_handler(self, id):
        self.logger.debug('controller Config changed signal received')

    def config_fetched_handler(self):
        self.logger.debug('controller Config signal received')
        self.set_comm_status('Connected')
        self.comm_state(3)

        if bool(conf.get('common.check_firmware_version')):
            if self.controller.check_firmware_version():
                msgBox = QtGui.QMessageBox()
                msgBox.setText(
                    'New firmware available.\n' +
                    self.controller.firmware_instructions())
                msgBox.exec_()

        max_velocity = max(
            float(self.controller.board_config['xvm']['value']),
            float(self.controller.board_config['yvm']['value']),
            float(self.controller.board_config['zvm']['value']))

        self.logger.debug('max velocity for all axis: xvm:')
        self.logger.debug(self.controller.board_config['xvm']['value'])
        self.logger.debug(
            ' yvm:' +
            self.controller.board_config['yvm']['value'])
        self.logger.debug(
            ' zvm:' +
            self.controller.board_config['zvm']['value'])
        self.logger.debug(' max' + str(max_velocity))

        self.ui.progressVelocity.setMaximum(float(max_velocity) * sqrt(2))

        # check coordinates for each axis installed
        positions = {}
        for axis_letter in sorted(self.controller.installed_axis):
            lcdelement = getattr(
                self.ui, "lcdMachNumber" + axis_letter.upper())

            # add the axis and last known position to a dictionary
            if conf.get('last_positions.' + axis_letter.lower()) is not None:
                last_axis_position = conf.get(
                    'last_positions.' +
                    axis_letter.lower())
                if lcdelement.value() != float(last_axis_position):
                    positions[axis_letter.lower()] = conf.get(
                        'last_positions.' + axis_letter.lower())

        # if there are axis that don't match the EPROM then prompt
        if len(positions) > 0:
            position_string = ''
            for axis_letter, (position) in positions.iteritems():
                position_string += axis_letter.upper() + str(position) + ' '

            message = '''
The last known coordinates of the machine\
do not match those stored on the controller
This could be due to a reset or powering off and on again.

Would you like to reset the \
controller to %s?
'''
            reply = QtGui.QMessageBox.question(
                self, 'Restore Coordinates',
                message % position_string,
                QtGui.QMessageBox.Yes,
                QtGui.QMessageBox.No)
            if reply == QtGui.QMessageBox.Yes:
                self.restore_last_positions()

        # flag the controller object to start
        # saving last known coordinates
        self.controller.track_coordinates = True

        self.visualiser.set_config.emit(
            'chord',
            float(self.controller.chord_length()))

    def timer_tick_handler(self, total):
        # self.logger.debug('timer_tick_handler ' + str(total))
        self.ui.lblOutputRuntime.setText(self.format_time(total))

    def idle_handler(self):
        self.logger.debug('idle_handler')

    def busy_handler(self):
        self.logger.debug('busy_handler')

    def format_time(self, seconds):
        hours, rest = divmod(floor(seconds), 3600)
        minutes, seconds = divmod(rest, 60)

        return '{:0>2d}:{:0>2d}:{:0>2d}'.format(
            int(hours),
            int(minutes),
            int(seconds))

    def disconnect_received_handler(self):
        self.logger.debug('controller Disconnected signal received')
        self.set_comm_status('Disconnected')
        self.comm_state(1)

    def home_received_handler(self, axis_letter, type):
        self.home_switch_found(axis_letter, type)

    def line_received_handler(self, line, log):
        if len(line) > 0 and log:
            self.logger.debug('Adding Status: > ' + line)
            self.add_status_line(' > ' + line)

    def line_sent_handler(self, line, log=False):
        if len(line) > 0 and log:
            self.logger.debug('Adding Status: < ' + line)
            self.add_status_line(' < ' + line)

    def reset_received_handler(self):
        self.set_comm_status('Connected')
        self.comm_state(3)
        self.ui.progressFileSend.setValue(0)
        self.ui.progressQueuedCommands.setValue(0)
        self.end_of_file_handler()

    def axis_received_handler(self, axis_letter):
        self.toggle_axis_visibility(axis_letter, True)

    def position_received_handler(self, axis_letter, position):
        self.visualiser.tool_position.emit(axis_letter, position)
        self.update_lcd(axis_letter, position)

    def velocity_received_handler(self, velocity):
        # update the gui to show the current velocity
        self.ui.progressVelocity.setValue(
            min(velocity, self.ui.progressVelocity.maximum()))
        self.logger.debug(
            'Setting velocity to: ' +
            str(velocity) +
            ' actual:' +
            str(self.ui.progressVelocity.value()))

    def feed_rate_sent_handler(self, rate):
        # add the feed rate to the gui and config
        index = self.ui.comboFeedRate.findText(rate)
        if index < 0:
            items = []
            for i in range(self.ui.comboFeedRate.count()):
                items.append(self.ui.comboFeedRate.itemText(i))
            items = sorted(items, key=int)
            self.ui.comboFeedRate.clear()
            self.ui.comboFeedRate.addItems(items)
        index = self.ui.comboFeedRate.findText(rate)
        conf.set('ui.feed_rate_index', index)
        self.ui.comboFeedRate.setCurrentIndex(index)

    def error_received_handler(self, state, message, value):
        self.show_error(state, message, value)

    def units_received_handler(self, unit_mode):
        self.set_units(unit_mode)

    def dist_mode_received_handler(self, dist_mode):
        self.logger.debug('dist_mode_received_handler ' + str(dist_mode))
        self.set_dist_mode(dist_mode)

    def programme_progress_handler(self, progress):
        if self.ui.progressFileSend.value() < 100:
            self.logger.debug('programme_progress_handler ' + str(progress))
            self.ui.progressFileSend.setValue(min(100, int(progress)))

    def queue_size_handler(self, size):
        self.ui.progressQueuedCommands.setValue(size)

    def end_of_file_handler(self):
        self.ui.btnPause.setEnabled(False)
        self.ui.btnClear.setEnabled(False)
        self.ui.btnStart.setEnabled(True)

        self.toggle_jog_ui_elements(True)

        # tinyg queue is hard to calc proper completion
        self.ui.progressFileSend.setValue(100)

        self.logger.debug('end_of_file_handler')
        self.controller.pause_timer()

    def start_of_file_handler(self):
        self.toggle_jog_ui_elements(False)

    def init_ui(self):
        self.logger.debug('Loading main window ui')
        self.ui = uic.loadUi('ui/mainwindow.ui', self)
        self.ui.setWindowTitle('Cender')
        self.ui.setWindowIcon(QtGui.QIcon('web.png'))

        geom_settings = conf.get('ui.geometry')
        if geom_settings is not None:
            self.restoreGeometry(QtCore.QByteArray.fromBase64(geom_settings))

        self.ui.show()

        # menu
        self.logger.debug('Setting up menus')
        self.ui.actionExit.setShortcut('Ctrl+Q')
        self.ui.actionExit.setStatusTip('Exit application')
        self.ui.actionExit.triggered.connect(QtGui.qApp.quit)
        self.ui.actionOptions.triggered.connect(self.show_options_window)
        self.ui.actionAbout.triggered.connect(self.show_about_window)
        self.ui.actionFull_screen.triggered.connect(self.full_screen)
        self.ui.actionFull_screen.setShortcut('F11')

        # ui elements
        self.logger.debug('Setting up UI events')
        self.ui.btnDisconnect.setHidden(True)
        self.ui.btnSwitchDistanceMode.setHidden(True)
        self.ui.btnFindHome.clicked.connect(self.btn_find_home_clicked)
        self.ui.btnConnect.clicked.connect(self.btn_connect_clicked)
        self.ui.btnDisconnect.clicked.connect(self.btn_disconnect_clicked)
        self.ui.btnZeroAll.clicked.connect(self.zero_all_axis)
        self.ui.btnOffsetZeroAll.clicked.connect(self.offset_zero_all_axis)

        self.ui.comboCommand.baseKeyPressEvent = \
            self.ui.comboCommand.keyPressEvent
        self.ui.comboCommand.keyPressEvent = self.command_key_press_event

        self.ui.btnGoHome.clicked.connect(self.go_home)
        self.ui.btnOffsetGoHome.clicked.connect(self.offset_go_home)
        self.ui.btnSoftReset.clicked.connect(self.soft_reset)
        self.ui.btnBackOff.clicked.connect(self.limit_back_off)
        self.ui.btnSwitchDistanceMode.clicked.connect(
            self.toggle_distance_mode)

        self.ui.checkBoxCoolant.clicked.connect(self.toggle_coolant)

        self.ui.comboStep.activated.connect(self.change_jog_step)
        self.ui.btnDecX.clicked.connect(self.decrement_x)
        self.ui.btnDecX.setShortcut('Left')
        self.ui.btnIncX.clicked.connect(self.increment_x)
        self.ui.btnIncX.setShortcut('Right')

        self.ui.btnDecY.clicked.connect(self.decrement_y)
        self.ui.btnDecY.setShortcut('Down')
        self.ui.btnIncY.clicked.connect(self.increment_y)
        self.ui.btnIncY.setShortcut('Up')

        self.ui.btnDecZ.clicked.connect(self.decrement_z)
        self.ui.btnDecZ.setShortcut('PgDown')
        self.ui.btnIncZ.clicked.connect(self.increment_z)
        self.ui.btnIncZ.setShortcut('PgUp')

        self.ui.btnDecA.clicked.connect(self.decrement_a)
        self.ui.btnDecA.setShortcut('Ctrl+Down')
        self.ui.btnIncA.clicked.connect(self.increment_a)
        self.ui.btnIncA.setShortcut('Ctrl+Up')

        self.ui.checkBoxSpindle.stateChanged.connect(self.spindle_toggle)
        self.ui.radioSpindleDirectionCW.clicked.connect(self.spindle_toggle)
        self.ui.radioSpindleDirectionCCW.clicked.connect(self.spindle_toggle)
        self.ui.comboSpindleSpeed.activated.connect(self.spindle_toggle)
        self.ui.comboFeedRate.activated.connect(self.set_feed_rate)

        self.ui.btnOpenFile.clicked.connect(self.select_file)
        self.ui.lineFilePath.textChanged.connect(self.validateFilePath)
        self.ui.btnStart.clicked.connect(self.send_file)
        self.ui.btnPause.clicked.connect(self.pause_resume)
        self.ui.btnClear.clicked.connect(self.clear)

        self.ui.comboOffset.activated.connect(self.change_offset)

        self.ui.lcdMachNumberX.customContextMenuRequested.connect(
            self.context_menu_lcd)
        self.ui.lcdMachNumberY.customContextMenuRequested.connect(
            self.context_menu_lcd)
        self.ui.lcdMachNumberZ.customContextMenuRequested.connect(
            self.context_menu_lcd)
        self.ui.lcdMachNumberA.customContextMenuRequested.connect(
            self.context_menu_lcd)

        self.ui.lcdWorkNumberX.customContextMenuRequested.connect(
            self.context_menu_lcd)
        self.ui.lcdWorkNumberY.customContextMenuRequested.connect(
            self.context_menu_lcd)
        self.ui.lcdWorkNumberZ.customContextMenuRequested.connect(
            self.context_menu_lcd)
        self.ui.lcdWorkNumberA.customContextMenuRequested.connect(
            self.context_menu_lcd)

        self.ui.textStatusArea.customContextMenuRequested.connect(
            self.context_menu_status)

        # set up some lists and default settings
        self.logger.debug('Adding step values')
        for stepdistance in [0.001, 0.01, 0.1, 1, 10, 100]:
            self.ui.comboStep.addItem(str(stepdistance))
        self.ui.comboStep.setCurrentIndex(int(conf.get('ui.jog_step_index')))

        self.logger.debug('Adding spindle speeds')
        for spindlespeed in range(5000, 30000, 5000):
            self.ui.comboSpindleSpeed.addItem(str(spindlespeed))
        self.ui.comboSpindleSpeed.setCurrentIndex(
            int(conf.get('ui.spindle_speed_index')))

        self.logger.debug('Adding feed rates')
        for feedrate in range(100, 1000, 100):
            self.ui.comboFeedRate.addItem(str(feedrate))

        if int(conf.get('ui.feed_rate_index')) >= len(self.ui.comboFeedRate):
            conf.set('ui.feed_rate_index', (len(self.ui.comboFeedRate) - 1))

        self.ui.comboFeedRate.setCurrentIndex(
            int(conf.get('ui.feed_rate_index')))

        self.set_offsets()

        self.ui.radioSpindleDirectionCW.setChecked(
            (int(conf.get('ui.spindle_direction')) == 0))
        self.ui.radioSpindleDirectionCCW.setChecked(
            (int(conf.get('ui.spindle_direction')) == 1))

        self.toggle_axis_visibility('a', False)
        # self.zero_all_lcds()

        # self.show_options_window() # options debug

        self.comm_state(1)
        self.zero_all_lcds()

        # self.camera_thread = Camera()
        # self.camera_thread.camera_frame = self.ui.cameraFrame
        # self.camera_thread.daemon = True
        # self.camera_thread.frameWidget = self.ui.cameraFrame
        # self.camera_thread.start()

        self.visualiserWidget = VisualisationWidget()
        self.ui.visualiserContainer.addWidget(self.visualiserWidget)

        self.visualiser = Visualiser(self.visualiserWidget)
        self.visualiser.daemon = True
        self.visualiser.start()

        # testing the visualisation widget without having
        # a board connected
        # self.visualiser.addToolPath('G3 X50 Y-50 Z-10 R-50')
        # self.visualiser.addToolPath('G2 X100 Y-100 Z-10 R50')
        # self.visualiser.addToolPath('G3 X0 Y0 Z0 I-50 J50')
        # self.visualiser.addToolPath('G19')
        # self.visualiser.addToolPath('G2 X100 Y0 Z0 J-50 P3')
        # self.visualiser.addToolPath('G17')
        # self.visualiser.addToolPath('G0 X0 Y0 Z0')
        # self.visualiser.addToolPath('G2 X0 Y0 Z-100 I-50 P3')

        # self.visualiser.setToolPosition(50,50,0)
        # self.visualiser.setToolPosition(50,50,-10)
        # self.visualiser.setToolPosition(50,100,0)

    def set_offsets(self):
        self.logger.debug('Setting up offsets')
        self.ui.comboOffset.clear()
        for offset_name in conf.get('ui.offset_names'):
            self.ui.comboOffset.addItem(str(offset_name))

        self.ui.comboOffset.setCurrentIndex(
            int(conf.get('ui.current_offset_index')))

    def show_camera_frame(self, frame):
        self.ui.lblCameraFrame.setPixmap(frame)
        self.ui.lblCameraFrame.setScaledContents(True)

    def full_screen(self):
        if self.isFullScreen():
            self.showNormal()
            self.setWindowFlags(
                self.windowFlags() & ~QtCore.Qt.FramelessWindowHint)
            self.show()
        else:
            self.setWindowFlags(
                self.windowFlags() | QtCore.Qt.FramelessWindowHint)
            self.showFullScreen()

    def show_options_window(self):
        options = OptionsWindow(self)

    def show_about_window(self):
        about = AboutWindow(self)

    def set_units(self, unit_mode):
        unit_text = '(inch)'
        if int(unit_mode) == 1:
            unit_text = '(mm)'

        self.ui.lblOutputUnitsMachine.setText(unit_text)
        self.ui.lblOutputUnitsWork.setText(unit_text)

        if int(unit_mode) == 1:
            self.ui.progressVelocity.setFormat('%v mm/min')
        else:
            self.ui.progressVelocity.setFormat('%v inch/min')

    def toggle_distance_mode(self):
        if self.ui.lblDistanceModeIndicator.text() == 'Relative':
            self.set_dist_mode(0)  # switch to absolute
            self.controller.set_distance_mode(0)
        else:
            self.set_dist_mode(1)  # switch to relative
            self.controller.set_distance_mode(1)

    def set_dist_mode(self, dist_mode):
        dist_text = 'Absolute'
        switch_text = 'rel'
        if int(dist_mode) == 1:
            dist_text = 'Relative'
            switch_text = 'abs'

        self.ui.lblDistanceModeIndicator.setText(dist_text)
        self.ui.btnSwitchDistanceMode.setText(switch_text)
        self.ui.btnSwitchDistanceMode.setHidden(False)

    def home_switch_found(self, axis_letter, type):
        if conf.get('ui.disable_homing') is not True:
            self.ui.btnFindHome.setEnabled(True)

    def context_menu_lcd(self, point):
        if self.controller.connected:
            lcd_element = self.sender()
            self.logger.debug(
                'context_menu_lcd ' + str(lcd_element.objectName()))
            self.lcd_menu = QtGui.QMenu(self)
            zero_action = QtGui.QAction('Zero', self)
            gotoAction = QtGui.QAction('Goto', self)
            resetAction = QtGui.QAction('Reset', self)
            homeAction = QtGui.QAction('Home', self)

            match = re.search(r'([A-Z])$', lcd_element.objectName())
            if match is not None:
                groups = match.groups()
                axis_letter = str(groups[0])
                if re.search(r'^lcdWork', lcd_element.objectName()):
                    zero_action.triggered.connect(
                        getattr(self, 'offset_zero_' + axis_letter.lower()))
                    gotoAction.triggered.connect(
                        partial(
                            getattr(self, 'goto'),
                            axis_letter=axis_letter,
                            offset=False))
                    resetAction.triggered.connect(
                        partial(
                            getattr(self, 'reset'),
                            axis_letter=axis_letter,
                            offset=False))
                else:
                    zero_action.triggered.connect(
                        getattr(self, 'zero_' + axis_letter.lower()))
                    gotoAction.triggered.connect(
                        partial(
                            getattr(self, 'goto'),
                            axis_letter=axis_letter,
                            offset=True))
                    resetAction.triggered.connect(
                        partial(
                            getattr(self, 'reset'),
                            axis_letter=axis_letter,
                            offset=True))

                    if len(self.controller.installed_homes) > 0 and \
                            self.controller.installed_homes.count(axis_letter.lower()) > 0 and \
                            conf.get('ui.disable_homing') is not True:
                        homeAction.triggered.connect(
                            partial(
                                getattr(self, 'find_axis_home'),
                                axis_letter=axis_letter))
                        self.lcd_menu.addAction(homeAction)

            self.lcd_menu.addAction(zero_action)
            self.lcd_menu.addAction(gotoAction)
            self.lcd_menu.addAction(resetAction)
            self.lcd_menu.popup(QtGui.QCursor.pos())

    def context_menu_status(self, point):
        status_element = self.sender()
        self.logger.debug(
            'context_menu_status ' + str(status_element.objectName()))
        self.status_menu = QtGui.QMenu(self)
        clearAction = QtGui.QAction('Clear', self)

        clearAction.triggered.connect(self.clear_status_list)
        self.status_menu.addAction(clearAction)
        self.status_menu.popup(QtGui.QCursor.pos())

    def clear_status_list(self):
        self.ui.textStatusArea.clear()

    def goto(self, axis_letter, offset=False):
        coordinate = float(getattr(
            self,
            'lcdWorkNumber' +
            axis_letter.upper()).value())
        format = "{0:." + str(conf.get('ui.lcd_precision')) + "f}"
        formatted_coord = format.format(coordinate)

        coordinate, ok = QtGui.QInputDialog.getText(
            self,
            'Goto',
            u'''
            Enter a new coordinate for the %s axis.
            \u2022 -20 or +20          absolute
            \u2022 --20 or ++20        relative
            \u2022 50%%                 percent of current position
            \u2022 ((here + 20) / 3.2) arithmetic
            ''' % axis_letter.upper(),
            QtGui.QLineEdit.Normal,
            formatted_coord)
        coordinate = str(coordinate).strip()

        if ok:
            # relative
            match = re.search(r'^(([\-\+])\2)[\d\.]+$', coordinate)
            if match is not None:
                self.logger.debug(coordinate)
                coordinate = re.sub(r'^([\-\+])\1', r'\1', coordinate)
                if coordinate == 0:
                    coordinate = abs(coordinate)
                self.logger.debug(coordinate)
                self.controller.move_axis(axis_letter, coordinate)
                return None

            # absolute
            match = re.search(r'^([\-\+])?[\d\.]+$', coordinate)
            if match is not None:
                self.controller.move_axis(axis_letter, coordinate, True)
                return None

            # percentage
            match = re.search(r'^([\d\.]+)\%$', coordinate)
            if match is not None:
                group = match.groups()
                if offset:
                    current_coordinate = getattr(
                        self, 'lcdWorkNumber' + axis_letter.upper()).value()
                else:
                    current_coordinate = getattr(
                        self, 'lcdMachNumber' + axis_letter.upper()).value()

                current_coordinate = (
                    current_coordinate * (float(group[0]) / 100))
                if current_coordinate == 0:
                    current_coordinate = abs(current_coordinate)

                self.controller.move_axis(
                    axis_letter, current_coordinate, True)
                return None

            # expresion
            match = re.search(r'^\(.+\)$', coordinate)
            if match is not None:
                if offset:
                    current_coordinate = getattr(
                        self, 'lcdWorkNumber' + axis_letter.upper()).value()
                else:
                    current_coordinate = getattr(
                        self, 'lcdMachNumber' + axis_letter.upper()).value()

                coordinate = re.replace(r'\bhere\b', current_coordinate)

                ns = {'__builtins__': None}
                new_coordinate = eval(coordinate, ns)

                if new_coordinate == 0:
                    new_coordinate = abs(new_coordinate)

                self.controller.move_axis(axis_letter, new_coordinate, True)
                return None

    def reset(self, axis_letter, offset=False):
        coordinate, ok = QtGui.QInputDialog.getText(
            self, 'Reset', 'Absolute coordinate to reset.')
        coordinate = str(coordinate).strip()

        if ok:
            # absolute
            match = re.search(r'^([\-\+])?[\d\.]+$', coordinate)
            if match is not None:
                self.controller.reset_axis(axis_letter, coordinate)

    def toggle_jog_ui_elements(self, state):
        elements_to_toggle = [
            "btnIncY", "btnDecY", "btnIncX", "btnDecX", "btnIncZ",
            "btnDecZ", "btnIncA", "btnDecA", "checkBoxSpindle",
            "comboSpindleSpeed", "radioSpindleDirectionCW",
            "radioSpindleDirectionCCW", "lblStep", "comboStep",
            "lblFeedRate", "comboFeedRate", "checkBoxCoolant",
            "btnGoHome", "btnOffsetGoHome", "btnZeroAll",
            "btnOffsetZeroAll", "comboOffset", "btnSwitchDistanceMode"]

        # if we have homing switches and homing isn't disabled
        if self.controller is not None and \
                len(self.controller.installed_homes) > 0 and \
                conf.get('ui.disable_homing') is not True:
            elements_to_toggle.append('btnFindHome')

        self.toggle_ui_state(state, elements_to_toggle)

    def toggle_all_ui_elements(self, state):
        elements_to_toggle = [
            "groupBoxSendFile", "lineFilePath", "btnOpenFile", "lblCommand",
            "comboCommand", "btnIncY", "btnDecY", "btnIncX", "btnDecX",
            "btnIncZ", "btnDecZ", "btnIncA", "btnDecA", "checkBoxSpindle",
            "comboSpindleSpeed", "radioSpindleDirectionCW",
            "radioSpindleDirectionCCW", "lblStep", "comboStep", "lblFeedRate",
            "comboFeedRate", "checkBoxCoolant", "btnGoHome",
            "btnOffsetGoHome", "btnZeroAll", "btnOffsetZeroAll",
            "comboOffset", "btnSwitchDistanceMode"]

        # if we have homing switches and homing isn't disabled
        if self.controller is not None and \
                len(self.controller.installed_homes) > 0 and \
                conf.get('ui.disable_homing') is not True:
            elements_to_toggle.append('btnFindHome')

        self.toggle_ui_state(state, elements_to_toggle)

    def toggle_ui_state(self, state, elements_to_toggle=[]):
        for uielement in elements_to_toggle:
            if hasattr(self.ui, uielement):
                self.logger.debug('      ' + uielement)
                uielementobj = getattr(self.ui, uielement)
                uielementobj.setEnabled(state)

    def pause_resume(self):
        if self.controller.pauseState:
            self.controller.resume()
            self.ui.btnPause.setText('Pause')
        else:
            self.controller.pause()
            self.ui.btnPause.setText('Resume')

    def clear(self):
        self.logger.debug('stopping and clearing')
        self.ui.btnPause.setEnabled(False)
        self.ui.btnPause.setText('Pause')
        self.ui.btnClear.setEnabled(False)
        self.ui.btnStart.setEnabled(True)
        self.toggle_jog_ui_elements(True)

        self.controller.pauseState = False
        self.controller.clear()
        self.controller.pause_timer()

    def send_file(self):
        file_path = self.ui.lineFilePath.text()
        conf.set('common.directory', os.path.dirname(str(file_path)))
        self.ui.btnPause.setEnabled(True)
        self.ui.btnClear.setEnabled(True)
        self.ui.btnStart.setEnabled(False)
        self.ui.lblOutputRuntime.setText(str(0))

        self.controller.send_file(file_path)

    def select_file(self):
        new_file_path = QtGui.QFileDialog.getOpenFileName(
            self,
            'Open GCode',
            conf.get('common.directory'),
            'All Files (*.*);;GCode (*.ngc *.gc *.txt);;Config (*.config)')
        if new_file_path != self.ui.lineFilePath.text():
            pub.sendMessage('programme-progress', progress=0)
        self.ui.lineFilePath.setText(new_file_path)

    def validateFilePath(self):
        file_path = self.ui.lineFilePath.text()

        if os.path.isfile(file_path):
            self.ui.btnStart.setEnabled(True)

            # send the file to the visualiser
            self.visualiser.clear.emit()

            content = ''
            with open(file_path) as f:
                content = f.read()

            if bool(conf.get('common.filter_file_commands')):
                content = self.controller.filter_file(content)
                # self.logger.debug('filtered file:' + content)

            file_match = re.search(r'\.ng?c$', file_path)
            if file_match is not None and conf.get('ui.show_visualiser'):
                self.tabControls.setCurrentPage(1)

            if content is not None and content != '':
                self.visualiser.add_commands.emit(content)

    def spindle_toggle(self):
        # filter and cast spindle speed
        spindle_speed = str(self.ui.comboSpindleSpeed.currentText().trimmed())
        spindle_speed = re.sub(r"\.[0-9]$", "", spindle_speed)
        spindle_speed = re.sub(r"[^\-0-9]", "", spindle_speed)

        # default to minimum spindle speed
        if len(spindle_speed) == 0 or spindle_speed <= 0:
            spindle_speed = int(conf.get('common.minimum_spindle_speed'))
        else:
            conf.set(
                'ui.spindle_speed_index',
                self.ui.comboSpindleSpeed.currentIndex())

        direction = 0
        if self.ui.radioSpindleDirectionCCW.isChecked():
            direction = 1

        conf.set('ui.spindle_direction', direction)

        self.controller.set_spindle(
            self.ui.checkBoxSpindle.isChecked(), spindle_speed, direction)

    def set_feed_rate(self):
        conf.set('ui.feed_rate_index', self.ui.comboFeedRate.currentIndex())
        self.controller.send('F' + str(self.ui.comboFeedRate.currentText()))

    def toggle_axis_visibility(self, axis_letter, visible):
        axis_letter = str(axis_letter).upper()

        self.logger.debug('toggle axis: ' + axis_letter)

        for uielement in [
                "lbl", "lcdMachNumber", "lcdWorkNumber", "btnDec", "btnInc",
                "lblJog"]:
            self.logger.debug('     ' + uielement + axis_letter)
            if hasattr(self.ui, uielement + axis_letter):
                uielementobj = getattr(self.ui, uielement + axis_letter)
                uielementobj.setHidden(not visible)

    def show_error(self, state, message, value):
        self.logger.debug(
            'show_error ' + str(state) + ', ' + message + ', ' + str(value))
        self.set_comm_status(message)
        if state == '27':
            self.logger.debug('Allow latch backoff')
            self.ui.btnBackOff.setEnabled(True)
        else:
            self.ui.btnBackOff.setEnabled(False)

        self.add_status_line('> Error: ' + message)

    def change_jog_step(self):
        conf.set('ui.jog_step_index', self.ui.comboStep.currentIndex())

    def decrement_x(self):
        stepdistance = self.ui.comboStep.currentText().trimmed()
        if len(stepdistance) > 0:
            self.controller.move_axis(
                "x", (float(self.ui.comboStep.currentText()) * -1))

    def increment_x(self):
        stepdistance = self.ui.comboStep.currentText().trimmed()
        if len(stepdistance) > 0:
            self.controller.move_axis(
                "x", float(self.ui.comboStep.currentText()))

    def decrement_y(self):
        stepdistance = self.ui.comboStep.currentText().trimmed()
        if len(stepdistance) > 0:
            self.controller.move_axis(
                "y", (float(self.ui.comboStep.currentText()) * -1))

    def increment_y(self):
        stepdistance = self.ui.comboStep.currentText().trimmed()
        if len(stepdistance) > 0:
            self.controller.move_axis(
                "y", float(self.ui.comboStep.currentText()))

    def decrement_z(self):
        stepdistance = self.ui.comboStep.currentText().trimmed()
        if len(stepdistance) > 0:
            self.controller.move_axis(
                "z", (float(self.ui.comboStep.currentText()) * -1))

    def increment_z(self):
        stepdistance = self.ui.comboStep.currentText().trimmed()
        if len(stepdistance) > 0:
            self.controller.move_axis(
                "z", float(self.ui.comboStep.currentText()))

    def decrement_a(self):
        stepdistance = self.ui.comboStep.currentText().trimmed()
        if len(stepdistance) > 0:
            self.controller.move_axis(
                "a", (float(self.ui.comboStep.currentText()) * -1))

    def increment_a(self):
        stepdistance = self.ui.comboStep.currentText().trimmed()
        if len(stepdistance) > 0:
            self.controller.move_axis(
                "a", float(self.ui.comboStep.currentText()))

    def go_home(self):
        self.logger.debug('go_home')
        self.controller.go_home()

    def offset_go_home(self):
        self.logger.debug('go_home')

        parameters = {}
        for axis_letter in self.controller.possible_axis:
            target_position = (
                getattr(
                    self.ui,
                    'lcdWorkNumber' + axis_letter.upper()).value() * -1)

            if target_position == 0:
                target_position = abs(target_position)

            parameters[axis_letter + '_position'] = target_position

        self.controller.move_multi_axis(**parameters)

    def toggle_coolant(self):
        self.logger.debug('Toggle coolant')
        self.controller.toggle_coolant(self.ui.checkBoxCoolant.isChecked())

    def soft_reset(self):
        self.controller.clear_command_queue()
        self.controller.soft_reset()
        self.controller.resume()

        self.controller.pause_timer()
        self.controller.reset_timer()

        self.set_comm_status('Connected')
        self.ui.btnBackOff.setEnabled(False)

    def limit_back_off(self):
        self.controller.limit_back_off()
        self.ui.btnBackOff.setEnabled(False)
        self.toggle_all_ui_elements(False)

    def add_status_line(self, line):
        self.ui.textStatusArea.appendPlainText(line)

    def set_comm_status(self, status_text):
        self.ui.lblBoardStatus.setText(status_text)

    def btn_connect_clicked(self):
        self.set_comm_status('Connecting')
        self.controller.connect()

    def btn_disconnect_clicked(self):
        self.set_comm_status('Disconnecting')
        self.controller.disconnect()

    def btn_find_home_clicked(self):
        self.logger.debug('btn_find_home_clicked')
        self.controller.find_home()

    def find_axis_home(self, axis_letter):
        self.logger.debug('finding axis home')
        self.controller.find_axis_home(axis_letter)

    def zero_all_axis(self):
        self.zero_x()
        self.zero_y()
        self.zero_z()
        self.zero_a()

    def zero_x(self):
        self.zero('x')

    def zero_y(self):
        self.zero('y')

    def zero_z(self):
        self.zero('z')

    def zero_a(self):
        self.zero('a')

    def zero(self, axis_letter):
        self.controller.zero_axis(axis_letter)
        self.update_lcd(axis_letter, 0)

    def offset_zero_all_axis(self):
        self.offset_zero_x()
        self.offset_zero_y()
        self.offset_zero_z()
        self.offset_zero_a()

    def offset_zero_x(self):
        self.offset_zero('x')

    def offset_zero_y(self):
        self.offset_zero('y')

    def offset_zero_z(self):
        self.offset_zero('z')

    def offset_zero_a(self):
        self.offset_zero('a')

    def offset_zero(self, axis_letter):
        lcdnumber = getattr(self.ui, 'lcdMachNumber' + axis_letter.upper())
        try:
            conf.set(
                'ui.offsets.' + str(conf.get('ui.current_offset_index')) +
                '.' + axis_letter, lcdnumber.value())
        except:
            conf.set(
                'ui.offsets.' + str(conf.get('ui.current_offset_index')) +
                '.' + axis_letter, 0)
            pass

        self.update_lcd(axis_letter, lcdnumber.value(), True)

    def zero_all_lcds(self):
        if self.controller is not None:
            for axis in self.controller.possible_axis:
                self.update_lcd(axis, 0)

    def update_lcd(self, axis_letter, position, only_offset=False):
        axis_letter = str(axis_letter)

        self.logger.debug(
            'update_lcd ' + axis_letter + ' ' + str(position) + ' ' +
            str(only_offset))
        if not only_offset:
            lcdelement = getattr(
                self.ui, "lcdMachNumber" + axis_letter.upper())
            lcdelement.display(
                ("{0:." + str(conf.get('ui.lcd_precision')) + "f}")
                .format(float(position)))

        offsetlcdelement = getattr(
            self.ui, "lcdWorkNumber" + axis_letter.upper())
        try:
            offset = conf.get(
                'ui.offsets.' + str(conf.get('ui.current_offset_index')) +
                '.' + axis_letter)
            if offset is None:
                raise Exception()
        except:
            offset = 0
            pass

        offsetlcdelement.display(
            ("{0:." + str(conf.get('ui.lcd_precision')) + "f}")
            .format(float(position) - float(offset)))

    def change_offset(self):
        conf.set('ui.current_offset_index', self.ui.comboOffset.currentIndex())

        for axis_letter in self.controller.possible_axis:
            # send it the current position to calculate from
            lcdelement = getattr(
                self.ui, "lcdMachNumber" + axis_letter.upper())
            self.update_lcd(axis_letter, lcdelement.value(), True)

    def send_command(self, text):
        currenttext = str(text)
        self.logger.debug("currenttext " + currenttext)

        # append the command
        # unless it is a duplicate of the last command in the history
        if self.ui.comboCommand.count() == 0 or \
                self.ui.comboCommand.findText(text) != \
                (self.ui.comboCommand.count() - 1):
            self.ui.comboCommand.addItem(currenttext)

        self.controller.send(currenttext)

    def resize_event(self, event):
        conf.set('ui.geometry', self.saveGeometry().toBase64())

    def command_key_press_event(self, event):
        if type(event) == QtGui.QKeyEvent:
            if event.key() == QtCore.Qt.Key_Enter or \
                    event.key() == QtCore.Qt.Key_Return:
                self.send_command(self.ui.comboCommand.currentText())

        self.ui.comboCommand.baseKeyPressEvent(event)

    def keyPressEvent(self, event):
        self.logger.debug('Key ' + str(event.key()) + ' key pressed')
