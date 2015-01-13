import serial
import logging
import time
import re
import math
import urllib2
import datetime
from configuration import conf
from controller_board import ControllerBoard
from pubsub import pub
from PyQt4 import QtGui
from functools import partial
import json


class TinyG(ControllerBoard):

    limit_hit_axis_letter = None
    limit_hit_axis_direction = None

    board_config = {}
    command_queue_slots = 28

    reset_pending = False
    board_name = 'TinyG 0.96'
    default_firmware_branch_name = 'master'

    def __init__(self, main_window):
        super(TinyG, self).__init__(main_window)
        self.logger.debug('TinyG driver initialised')

    # event handlers
    def reset_received_handler(self):
        return True

    def is_connected(self, port, baud, stopbits, parity, flow):
        test_port = serial.Serial(
            port,
            baud,
            timeout=0,
            writeTimeout=10,
            stopbits=stopbits,
            parity=parity,
            rtscts=(flow == 'rtscts'),
            xonxoff=(flow == 'xonxoff'))
        test_port.flush()

        test_port.write("$fv\n")
        time.sleep(2)
        response = ''
        while test_port.isOpen() and test_port.inWaiting() > 0:
            response += test_port.read(200)

        self.logger.debug(response)

        match = re.search(r'firmware version +[\d\.]+\n', response.strip())
        if match is not None:
            return True
        return False

    def disconnect(self):
        # super(TinyG, self).disconnect()
        self.main_window.set_comm_status('Disconnecting')
        self.logger.debug('Disconnecting from TinyG')
        try:
            self.logger.debug('Disconnection from TinyG succeeded')

            pub.sendMessage('disconnectReceived')

            return True
        except:
            self.logger.debug('Disconnection from TinyG failed')
            self.connected = True
            return False

    def statusInterval(self):
        interval = super(TinyG, self).statusInterval()
        if 'si' in self.board_config:
            interval = (float(self.board_config['si']['value']) / 1000)

        return float(interval)

    def connect(self):
        self.logger.debug(
            'Connecting to TinyG on ' + conf.get('connection.port.name') +
            ' @ ' + str(conf.get('connection.port.baud')))
        self.main_window.set_comm_status('Connecting')

        use_rtscts = (conf.get('connection.port.flow_control') == 'rtscts')
        use_xonxoff = (conf.get('connection.port.flow_control') == 'xonxoff')
        try:
            self.port = serial.Serial(
                conf.get('connection.port.name'),
                int(conf.get('connection.port.baud')),
                timeout=int(conf.get('connection.port.read_timeout')),
                writeTimeout=int(conf.get('connection.port.write_timeout')),
                stopbits=int(conf.get('connection.port.stopbits')),
                parity=conf.get('connection.port.parity')[0].upper(),
                rtscts=use_rtscts,
                xonxoff=use_xonxoff)
            self.port.flush()

            # set text mode
            self.clear_command_queue()
            command = '$ee=0'
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (echo off)'
            self.send(command, False)

            pub.subscribe(self.connect_received_handler, 'connect-received')
            self.echo_back('connect')

            time.sleep(10)
            if not self.connected:
                raise Exception()
        except:
            self.logger.debug('Connection to TinyG failed')
            self.connected = False
            pub.sendMessage('disconnect-received')

        return False

    def enable_json_mode(self):
        command = '$ej=1'
        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (json mode)'
        self.send(command, False)

    def parse_reset(self, response):
        if self.reset_pending and 'msg' in response and \
                response['msg'] == "SYSTEM READY":
            pub.sendMessage('reset-received')
            self.reset_pending = False

            return False

        return True

    def parse_config(self, line):
        # match config information
        # ([\d\.\-\w]+)(.{0})                       2X2660-FHZ
        # ([\d+\.]+) ((?:\[)[^\]]+(?:\]))         1 [standard]
        # ([\d+\.]+) (\w+\/\w+(?:\^\d))           500000000.0 mm/min^3
        # ([\d+\.]+) (\w{2,3}).*                  0.0100 mm (larger is faster)
        patterns = [
            '([\d\.\-\w]+)(.{0})',
            '([\d+\.]+) (?:\[)([^\]]+)(?:\])',
            '([\d+\.]+) (\w+\/\w+(?:\^\d))',
            '([\d\-\.]+) (\w{2,3}).*']
        for pattern in patterns:
            config_re = re.compile(
                '^\[([^\]]+)\] +([\w ]{0,10}[a-zA-Z ]+) ' + pattern + '$')
            match = re.search(config_re, line)
            if match is not None:
                groups = tuple(filter(None, match.groups()))
                try:
                    self.logger.debug(
                        'Config: ' + str(groups[0]) + ' ' + str(groups[1]) +
                        ' ' + str(groups[2]))
                    self.board_config[groups[0]] = {
                        'id': groups[0],
                        'message': groups[1].strip(),
                        'value': groups[2]}
                    if len(groups) == 4:
                        self.board_config[groups[0]]['units'] = groups[3]

                except IndexError:
                    print groups
                    self.logger.debug(
                        'IndexError: ' + line + '\n' + str(len(groups)))

                return False

        return True

    def parse_queue_report(self, response):
        # check queue report and set/clear flag to send
        if 'qr' in response:
            free_queue_slots = int(response['qr'])
            queue_size = (self.command_queue_slots - free_queue_slots)
            self.logger.debug('queue_size: ' + str(queue_size))

            if self.sender_thread is not None:
                if free_queue_slots > 1:
                    self.sender_thread.ready.emit()
                else:
                    self.sender_thread.block.emit()

            pub.sendMessage('queue-size', size=queue_size)

            return False

        return True

    def parse_position(self, response):
        if 'sr' in response:
            for axis_letter in ['x', 'y', 'z']:
                if 'pos' + axis_letter in response['sr']:
                    coordinate = response['sr']['pos' + axis_letter]
                    self.logger.debug(
                        'Stat: ' + axis_letter + ':' + str(coordinate))
                    pub.sendMessage(
                        'position-received',
                        axis_letter=axis_letter,
                        position=float(coordinate))

                    if self.track_coordinates:
                        conf.set(
                            'last_positions.' + axis_letter.lower(),
                            float(coordinate))

            if 'vel' in response['sr']:
                pub.sendMessage(
                    'velocity-received', velocity=int(response['sr']['vel']))

            return False

        return True

    def parse_status(self, response):
        if 'sr' in response and 'stat' in response['sr']:
            if response['sr']['stat'] in [3, 4]:
                pub.sendMessage('idle')
            if response['sr']['stat'] in [5]:
                pub.sendMessage('busy')
            return False

        return True

    def parse_errors(self, response):
        # match status reports
        if 'er' in response:
            error_message = response['er']['msg']
            error_code = int(response['er']['st'])
            error_value = None
            if 'val' in response['er']:
                error_value = int(response['er']['val'])

            self.logger.debug(
                'Error: ' + str(error_message) + ' ' + str(error_code))

            # limit message
            if error_code == 27:
                self.pause()

                message += ', '
                if error_value in [0, 2, 4, 6]:
                    self.limit_hit_axis_direction = 0
                else:
                    self.limit_hit_axis_direction = 1

                if error_value in [0, 1]:
                    self.limit_hit_axis_letter = self.possible_axis[0]
                if error_value in [2, 3]:
                    self.limit_hit_axis_letter = self.possible_axis[1]
                if error_value in [4, 5]:
                    self.limit_hit_axis_letter = self.possible_axis[2]
                if error_value in [6, 7]:
                    self.limit_hit_axis_letter = self.possible_axis[3]

                message += self.limit_hit_axis_letter.upper()
                if self.limit_hit_axis_direction == 0:
                    message += 'min'
                else:
                    message += 'max'
                message += ' limit hit'

            self.logger.debug(
                'Sending error data :' + str(error_code) + ' ' +
                error_message + ' ' + str(error_value))
            pub.sendMessage(
                'error-received',
                state=error_code,
                message=error_message,
                value=error_value)

            # don't use normal status line method
            # handled in main_window errorReceived sub
            return False

        return True

    def parse_echo(self, response):
        # trigger an echo back event
        if 'msg' in response:
            session_re = re.compile('_' + self.session_id + '_')
            match = re.search(session_re, response['msg'])

            if match is not None:
                pub.sendMessage(
                    re.sub(session_re, '', response['msg']) + '-received')
                return False

        return True

    # analyse requests to the board
    def parse_request(self, line):
        log = super(TinyG, self).parse_request(line)

        if line == '{"sr":""}':
            log = False

        return log

    # analyse the response from the board and react to the contents
    def parse_response(self, line):
        self.logger.debug('Parsing response: ' + line)
        log = True

        try:
            response = json.loads(line)

            if isinstance(response, dict):

                if 'r' in response:
                    response = response['r']

                if len(response) == 0 or 'rx' in response or '' in response:
                    log = False

                log = self.parse_reset(response) and log

                log = self.parse_queue_report(response) and log

                log = self.parse_position(response) and log

                log = self.parse_errors(response) and log

                log = self.parse_status(response) and log

                log = self.parse_echo(response) and log

        except ValueError:
            self.logger.debug('response wasn\'t json')
            pass

        log = self.parse_config(line) and log

        return log

    def connect_received_handler(self):
        pub.unsubscribe(self.connect_received_handler, 'connect-received')
        self.logger.debug('Connection to TinyG succeeded')
        self.connected = True
        # self.set_distance_mode(0)
        self.enable_flow_control()
        self.fetch_board_config()

        self.check_firmware_version()

    def check_firmware_version(self):
        self.logger.debug('Checking firmware version')

        branch = conf.get('tinyg.firmware_branch')
        if branch is None:
            branch = self.default_firmware_branch_name
            conf.set('tinyg.firmware_branch', branch)

        try:
            response = urllib2.urlopen(
                'https://raw.githubusercontent.com/synthetos/TinyG/' +
                branch + '/firmware/tinyg/tinyg.h')
            html = response.read()

            match = re.search(
                r'\#define TINYG_FIRMWARE_BUILD\s+([\d\.]+)', html)

            if 'fb' in self.board_config and match is not None:
                groups = match.groups()
                self.logger.debug(
                    ' Found ' + groups[0] + ' and we are ' +
                    self.board_config['fb']['value'])
                return (
                    float(groups[0]) > float(self.board_config['fb']['value'])
                )
        except urllib2.URLError:
            pass

        return False

    def firmware_instructions(self):
        branch = conf.get('tinyg.firmware_branch')
        if branch is None:
            branch = self.default_firmware_branch_name
            conf.set('tinyg.firmware_branch', branch)

        return 'Goto https://github.com/synthetos/TinyG/tree/' + branch

    def config_fetched_handler(self):
        self.logger.debug('config_fetched_handler')

        # trigger event for found axis
        for motor_index in range(1, 5):
            if (str(motor_index) + 'ma') in self.board_config:
                axis_config = self.board_config[str(motor_index) + 'ma']
                axis_letter = self.possible_axis[int(axis_config['value'])]
                self.logger.debug('Found axis: ' + axis_letter)

                if self.installed_axis.count(axis_letter) == 0:
                    self.installed_axis.append(axis_letter)
                pub.sendMessage('axis-received', axis_letter=axis_letter)

        # notify of board units
        if 'gun' in self.board_config:
            pub.sendMessage(
                'units-received',
                unit_mode=self.board_config['gun']['value'])
            self.set_units(
                metric=(self.board_config['gun']['value'] == '1'),
                imperial=(self.board_config['gun']['value'] == '0'))

        if 'gdi' in self.board_config and self.absolute is None:
            self.absolute = (self.board_config['gdi']['value'] == '0')
            pub.sendMessage(
                'dist-mode-received',
                dist_mode=self.board_config['gdi']['value'])

        # notify of home switches
        for axis_letter in self.possible_axis:
            for postfix in ['sn', 'sx']:
                if (axis_letter + postfix) in self.board_config:
                    switch_config = self.board_config[axis_letter + postfix]
                    if (switch_config['value'] == '1' or
                            switch_config['value'] == '3') and \
                            self.installed_homes.count(axis_letter) == 0:
                        self.installed_homes.append(axis_letter)
                        pub.sendMessage(
                            'home-received',
                            axis_letter=axis_letter,
                            type=switch_config['value'])

        pub.sendMessage('config-fetched')

    def echo_back(self, flag):
        self.send('{"msg":"_' + self.session_id + '_' + flag + '"}')

    def fetch_board_config(self):
        pub.subscribe(self.config_fetched_handler, 'config-received')

        self.fetch_position()

        command = '$$'
        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (config)'

        self.send(command)
        self.echo_back('config')

    # this is a pre filter to just remove some lines
    def filter_response(self, line):
        line = re.sub(r"^tinyg \[[^\]]+\] ok\>\s*", "", line)
        return line

    def filter_request(self, line):
        line = super(TinyG, self).filter_request(line)

        return line

    def request_command_queue_size(self):
        command = '$qr'

        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (queue report)'

        self.send(command)

    def fetch_position(self):
        self.send('{"sr":""}')

    def fetch_units(self):
        self.send('{"sr":""}')

    def enable_queue_reports(self):
        command = '$qv=1'
        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (enable verbose queue reports)'
        self.send(command)

    def enable_flow_control(self):
        command = '$ex=2'
        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (hardware flow control)'
        self.send(command)

    def find_home(self):

        if conf.get('ui.disable_homing'):
            return None

        command = ''

        for axis in self.installed_homes:
            lcdelement = getattr(
                self.main_window.ui, 'lcdMachNumber' + axis.upper())
            if lcdelement.isEnabled():
                self.logger.debug(axis + ' ' + str(lcdelement.value() * -1))
                command += (axis + '0')

        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (homing)'

        if command != '':
            self.send('G28.2 ' + command)

    def find_axis_home(self, axis_letter):
        self.logger.debug('Find home for ' + axis_letter)
        if self.installed_homes.count(str(axis_letter).lower()) > 0:
            command = 'G28.2 ' + axis_letter + '0'
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (homing ' + axis_letter + ' axis)'
            self.send(command)

    def go_home(self):
        parameters = {'absolute': True}
        for axis in self.installed_axis:
            lcdelement = getattr(
                self.main_window.ui, 'lcdMachNumber' + axis.upper())
            if lcdelement.isEnabled():
                self.logger.debug(axis + ' ' + str(lcdelement.value() * -1))
                parameters[axis + '_position'] = '0'

#    self.set_distance_mode(0)
        self.move_multi_axis(**parameters)

    def zero_all_axis(self):
        command = 'G92 '
        for axis in self.installed_axis:
            lcdelement = getattr(
                self.main_window.ui, 'lcdMachNumber' + axis.upper())
            if lcdelement.isEnabled():
                self.logger.debug(axis + ' ' + str(lcdelement.value() * -1))
                command += (axis + '0')
        self.send(command)

    def clear_command_queue(self):
        command = '%'
        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (clear command queue)'
        self.send(command, True, True)

    def soft_reset(self):
        self.reset_pending = True
        self.send('\x18 (reset)', True, True)
        self.clear_command_queue()
        self.enable_queue_reports()
        self.enable_flow_control()
        self.enable_json_mode()

    def limit_back_off(self):
        self.logger.debug('Latch backoff stage 1')
        if self.limit_hit_axis_letter is not None and \
                self.limit_hit_axis_direction is not None and \
                self.limit_hit_axis_letter in self.installed_axis:

            self.backoff_distance = self.board_config[
                self.limit_hit_axis_letter + 'lb']['value']
            self.backoff_distance_sign = ''
            if self.limit_hit_axis_direction == 1:
                self.backoff_distance_sign = '-'

            if self.backoff_distance is not None and \
                    len(self.backoff_distance) > 0 and \
                    float(self.backoff_distance) > 0:
                pub.subscribe(self.limit_back_offStage2, 'reset-received')
                self.soft_reset()

    def limit_back_offStage2(self):
        self.logger.debug('Latch backoff stage 2')
        pub.unsubscribe(self.limit_back_offStage2, 'reset-received')

        self.set_distance_mode(1)

        command = self.movement_gcode + ' ' + self.limit_hit_axis_letter + \
            self.backoff_distance_sign + self.backoff_distance
        if self.movement_gcode == 'G1':
            command += ' F' + \
                self.main_window.ui.comboFeedRate.currentText().trimmed()

        self.send(command)
        time.sleep(1)

        self.backoff_distance = None
        subreturn = pub.subscribe(self.limit_back_offStage3, 'reset-received')
        self.logger.debug(str(subreturn))
        self.soft_reset()

    def limit_back_offStage3(self):
        # TODO check if we are backing off of a homing switch
        # if self.board_config[self.limit_hit_axis_letter+'zb']['value']:
        zero_backoff = self.board_config[
            self.limit_hit_axis_letter + 'zb']['value']
        self.logger.debug('Latch backoff stage 3 ' + str(zero_backoff))
        pub.unsubscribe(self.limit_back_offStage3, 'reset-received')
        command = self.movement_gcode + ' ' + self.limit_hit_axis_letter + \
            self.backoff_distance_sign + zero_backoff

        if self.movement_gcode == 'G1':
            command += ' F' + \
                str(self.main_window.ui.comboFeedRate.currentText().trimmed())

        self.send(command)
        self.set_distance_mode(0)
        self.backoff_distance_sign = None
        self.limit_hit_axis_letter = None

        pub.subscribe(self.limit_back_offStage4, 'idle-received')

    def limit_back_offStage4(self):
        pub.unsubscribe(self.limit_back_offStage4, 'idle-received')
        pub.sendMessage('reset-received')

    def clear(self):
        super(TinyG, self).clear()
        self.logger.debug('tinyg stopping and clearing')
        self.send('!%~ (stop and clear)', True, True)
        self.pauseState = False
        self.reset_timer()

    def pause(self):
        self.logger.debug('tinyg pauseing')
        self.send('! (stop)', True, True)
        self.pauseState = True
        self.pause_timer()
        super(TinyG, self).pause()

    def resume(self):
        self.send('~ (resume)', True, True)
        self.pauseState = False
        self.resume_timer()
        super(TinyG, self).resume()

    def move_axis(self, axis, position, absolute=False):
        original_absolute = self.absolute

        self.set_distance_mode(int((absolute is False)))
        command = self.movement_gcode + ' ' + axis + str(position)
        if self.movement_gcode == 'G1':
            command += ' F' + \
                str(self.main_window.ui.comboFeedRate.currentText().trimmed())
        self.send(command)

        # return to relative if we switched
        if original_absolute != absolute:
            self.set_distance_mode(int(absolute))

    def move_multi_axis(
            self, x_position=None, y_position=None, z_position=None,
            a_position=None, absolute=False):
        command = ''
        if x_position is not None and self.installed_axis.count('x') > 0:
            command += 'x' + str(x_position)
        if y_position is not None and self.installed_axis.count('y') > 0:
            command += 'y' + str(y_position)
        if z_position is not None and self.installed_axis.count('z') > 0:
            command += 'z' + str(z_position)
        if a_position is not None and self.installed_axis.count('a') > 0:
            command += 'a' + str(a_position)

        if len(command):
            original_absolute = self.absolute

            if self.movement_gcode == 'G1':
                command += ' F' + \
                    str(self.main_window.ui.comboFeedRate.currentText(
                    ).trimmed())

            self.set_distance_mode(int((absolute is False)))
            self.send(self.movement_gcode + ' ' + command)
            if original_absolute != absolute:
                self.set_distance_mode(int((absolute)))

    def save_options(self, ui):
        custom_tab = ui.tabWidget.widget(ui.tabWidget.count() - 1)
        # check all checkboxes
        for check_box in custom_tab.findChildren(QtGui.QCheckBox):
            if check_box.objectName() == 'tinyg_edge_firmware':
                if check_box.isChecked():
                    conf.set('tinyg.firmware_branch', 'edge')
                else:
                    conf.set(
                        'tinyg.firmware_branch',
                        self.default_firmware_branch_name)

    def add_tab_to_config(self, ui):
        # return None # no config for now

        tinyg_vbox = QtGui.QVBoxLayout()

        btnExportSettings = QtGui.QPushButton('Export config')
        btnExportSettings.clicked.connect(
            partial(
                getattr(self, 'export_settings'),
                options_window=ui.window()))
        if not self.connected:
            btnExportSettings.setEnabled(False)
        tinyg_vbox.addWidget(btnExportSettings)

        checkBoxEdgeFirmware = QtGui.QCheckBox('Use Edge firmware branch')
        checkBoxEdgeFirmware.setObjectName('tinyg_edge_firmware')
        if conf.get('tinyg.firmware_branch') == 'edge':
            checkBoxEdgeFirmware.setChecked(True)

        tinyg_vbox.addWidget(checkBoxEdgeFirmware)
        tinyg_vbox.addStretch(1)

        tinyg_widget = QtGui.QWidget()
        tinyg_widget.setLayout(tinyg_vbox)
        ui.tabWidget.addTab(tinyg_widget, 'TinyG')

    def export_settings(self, options_window):
        read_only_settings = ['fb', 'fv', 'hv', 'id']
        now = datetime.datetime.fromtimestamp(
            time.time()).strftime('%Y-%m-%d_%H:%M:%S')

        filename = QtGui.QFileDialog.getSaveFileName(
            options_window, 'Choose Filename',
            conf.get('common.directory') + '/' + now + '_tinyg-' +
            self.board_config['fb']['value'] + '-' +
            self.board_config['id']['value'] + '.config',
            'Config (*.config)')

        if len(filename) > 0:
            with open(filename, 'a') as export_file:
                for config_item in sorted(self.board_config):
                    found = read_only_settings.count(
                        self.board_config[config_item]['id'])
                    if found == 0:
                        export_file.write(
                            '$' + self.board_config[config_item]['id'] + '=' +
                            self.board_config[config_item]['value'] + ' (' +
                            self.board_config[config_item]['message'] + ')\n')
