import serial
import logging
import time
import re
import os
import random
import string
import threading
from configuration import conf
from PyQt4 import QtCore
from pubsub import pub


class ControllerBoardListener(QtCore.QThread):
    line_received = QtCore.pyqtSignal(str)
    controller = None
    exit_loop = False

    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        # super(ControllerBoardListener, self).__init__(parent)
        self.logger = logging.getLogger(__name__)

    def receive(self):
        line = ''
        delay = self.controller.statusInterval() / 10
        timeout = 0
        while timeout < (2000 * delay) and self.exit_loop is False:
            try:
                if self.controller.port is not None and \
                        self.controller.port.isOpen() and \
                        self.controller.port.inWaiting() > 0:
                    try:
                        character = self.controller.port.read(1)
                        # self.logger.debug(
                        #    str(round(time.time() * 1000)) +' Received: ' +
                        #    character + '('+ str(ord(character)) +')')
                    except:
                        time.sleep(delay)
                        continue

                    if character != chr(13) and character != chr(10):
                        line += character
                        timeout = 0
                    else:

                        self.logger.debug(
                            str(round(time.time() * 1000)) +
                            ' Received Line: ' +
                            line)
                        if len(line) > 0:
                            self.logger.debug(' Line has length')
                            self.line_received.emit(line)
                            line = ''

                else:
                    # self.logger.debug(
                    #    str(round(time.time() * 1000)) +
                    #    ' Waiting for response')
                    timeout += delay
                    time.sleep(delay)
            except IOError:
                self.logger.debug('IOError')
                break
                pass
        self.logger.debug('Listener Exiting')
        self.exit = False

    def run(self):
        self.receive()

    def exit(self):
        self.logger.debug('Setting Exit flag')
        self.exit_loop = True


from collections import deque


class ControllerBoardSender(QtCore.QThread):

    ready = QtCore.pyqtSignal()
    block = QtCore.pyqtSignal()
    line_sent = QtCore.pyqtSignal(str)
    controller = None

    def __init__(self, parent=None, queue_name=False):
        QtCore.QThread.__init__(self, parent)
        self.logger = logging.getLogger(__name__ + ':' + queue_name)
        self.ready.connect(self.ready_received_handler)
        self.block.connect(self.block_received_handler)
        self.commands = deque([])

        self.log_command = False

        self.paused = False
        self.clear_to_send = True

    def send_line(self, controller, line):
        if self.controller.port is not None and self.controller.port.isOpen():
            if self.log_command:
                self.logger.debug('Sender sending ' + line)
            bytes = self.controller.port.write(line + '\n')
            if self.log_command:
                self.logger.debug('wrote ' + str(bytes) + ' bytes')
        if self.log_command:
            self.line_sent.emit(line)
        # controller.requestCommandQueueSize()

    def send(self, controller):
        delay = controller.statusInterval()
        while len(self.commands) > 0:
            if self.paused or not self.clear_to_send:
                self.logger.debug('Sender is blocked/paused')
            else:
                if self.log_command:
                    self.logger.debug(
                        'command queue size: ' + str(len(self.commands)))
                    if len(self.commands) > 0:
                        self.logger.debug(
                            ' the first element is ' + self.commands[0])
                command = self.commands.popleft()

                if self.log_command:
                    self.logger.debug('Sender thread sending ' + str(command))

                self.send_line(controller, command)

            # if we don't pause we lock up pyserial
            time.sleep(delay)

    def append_commands(self, commands):
        if self.log_command:
            self.logger.debug('appending ' + str(len(commands)) + ' commands')
        for command in commands:
            if len(command) > 0:
                self.commands.append(command)
                if self.log_command:
                    self.logger.debug(
                        'first command is ' +
                        self.commands[len(self.commands) - 1])

    def prepend_commands(self, commands):
        if self.log_command:
            self.logger.debug('prepending ' + str(commands))
        commands.reverse()
        for command in commands:
            if len(command) > 0:
                self.commands.append(command)
                if self.log_command:
                    self.logger.debug('first command is ' + self.commands[0])

    def ready_received_handler(self):
        if self.log_command:
            self.logger.debug('ready to send')
        self.clear_to_send = True

    def block_received_handler(self):
        if self.log_command:
            self.logger.debug('blocking send')
        self.clear_to_send = False

    def pause(self):
        if self.log_command:
            self.logger.debug('pauseing sender')
        self.paused = True

    def resume(self):
        if self.log_command:
            self.logger.debug('resumeing sender')
        self.paused = False

    def reset(self):
        if self.log_command:
            self.logger.debug('resetting sender')
        self.pause()
        self.commands = deque([])
        self.resume()

    def run(self):
        if self.controller is not None:
            self.clear_to_send = True
            if self.log_command:
                self.logger.debug('Sender thread started')
            self.send(self.controller)
        else:
            if self.log_command:
                self.logger.debug('Sender thread started without a controller')


class FileTimer(QtCore.QThread):
    last_start_time = None
    total = 0
    paused = False
    timer_tick = QtCore.pyqtSignal(float)

    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.logger = logging.getLogger(__name__)

    def go(self):
        self.last_start_time = time.time()
        # threading.Timer(0.5, self.report_time).start()
        self.report_time()

    def report_time(self):
        # self.logger.debug('currently paused:' + str(self.paused))
        if self.paused is False and self.last_start_time is not None:
            self.timer_tick.emit(
                self.total + (time.time() - self.last_start_time))
        threading.Timer(0.5, self.report_time).start()

    def reset(self):
        self.last_start_time = None
        self.total = 0

    def pause(self):
        self.logger.debug('pause timer')
        self.paused = True

        if self.last_start_time is not None:
            self.total += (time.time() - self.last_start_time)

    def resume(self):
        self.last_start_time = time.time()
        self.paused = False

    def run(self):
        self.go()


class ControllerBoard(QtCore.QObject):

    possible_axis = ['x', 'y', 'z', 'a']
    installed_axis = list()
    installed_homes = list()
    track_coordinates = False

    connected = False
    listener_thread = None
    sender_thread = None
    control_sender_thread = None
    timer_thread = None
    paused = False
    logging = True
    movement_gcode = 'G0'
    port = None
    absolute = None

    number_of_commands = 0
    commands_executed = 0
    queue_size = 0
    tracking_progress = False
    session_id = None

    def statusInterval(self):
        return 0.5

    def __init__(self, main_window, parent=None):
        # QtCore.QThread.__init__(self, parent)
        super(ControllerBoard, self).__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.main_window = main_window
        self.connected = False
        self.session_id = self.id_generator(20)

        # setup event handlers
        pub.subscribe(self.reset_received_handler, 'reset-received')
        pub.subscribe(self.queue_size_handler, 'queue-size')
        pub.subscribe(self.start_of_file_handler, 'start-of-file-received')
        pub.subscribe(self.end_of_file_handler, 'end-of-file-received')

    def queue_size_handler(self, size):
        if self.sender_thread is not None and self.sender_thread.isRunning():
            # block only the default sender thread
            # the control sender must not be blocked
            if size < (self.command_queue_slots - 4):
                self.sender_thread.ready.emit()
            else:
                self.sender_thread.block.emit()

    def id_generator(
            self,
            size=6,
            chars=string.ascii_lowercase + string.digits):
        return ''.join(random.choice(chars) for _ in range(size))

    def listener(self):
        self.logger.debug('Listening')
        # threading.Thread(target=self.receiveLine)
        self.listener_thread = ControllerBoardListener()
        self.listener_thread.daemon = True
        self.listener_thread.controller = self
        self.listener_thread.line_received.connect(self.line_received_handler)
        self.listener_thread.start()

    def timer(self):
        if self.timer_thread is None:
            self.logger.debug('Start file timer')
            self.timer_thread = FileTimer()
            self.timer_thread.daemon = True
            self.timer_thread.timer_tick.connect(self.timer_tick_handler)
            self.timer_thread.start()
        else:
            self.timer_thread.reset()

    def timer_tick_handler(self, total):
        pub.sendMessage('timer-tick', total=total)

    def end_of_file_handler(self):
        self.logger.debug('End Of File Handler')
        pub.sendMessage('end-of-file')

    def start_of_file_handler(self):
        self.logger.debug('Start Of File Handler')
        pub.sendMessage('start-of-file')

    def sender(self, commands, prepend=False, control=False):
        self.logger.debug('Sender ' + str(type(commands)))

        if type(commands) is str:
            self.logger.debug('splitting ' + str(type(commands)))
            commands = commands.split('\n')

            self.logger.debug('split ' + str(len(commands)))
        else:
            self.logger.debug('not splitting ' + str(type(commands)))

        self.logger.debug('commands ' + str(type(commands)))

        # filter and count the commands
        filtered_commands = []
        for command in commands:
            if control is True:
                filtered_commands.append(command)
            else:
                self.logger.debug('filtering ' + command)
                command = self.filter_request(command.strip())
                self.logger.debug(
                    'filtered ' + command + ' ' + str(len(command)))

                if command is not None and len(command) > 0:
                    match = re.search(r'^(?:M|G|T|S|F)(\d+)', command)
                    if match is not None:
                        # groups = match.groups()
                        # if ['0','1','2','3'].count(groups[0]) >0:
                        self.number_of_commands += 1

                        # add three more queue planner slots for archs
                        match = re.search(r'^G0?[23]', command)
                        if match is not None:
                            self.number_of_commands += 3

                        self.logger.debug(
                            'command counter now at ' +
                            str(self.number_of_commands))

                    filtered_commands.append(command)

                    # self.logger.debug(
                    #    'filtered_commands '+ str(filtered_commands))

        if control:
            self.control_sender(filtered_commands)
        else:
            self.default_sender(filtered_commands, prepend)

    def default_sender(self, commands, prepend=False):
        # start a new sender or add the new commands to the command queue
        if self.sender_thread is None or not self.sender_thread.isRunning():
            self.logger.debug('New sender')

            self.sender_thread = ControllerBoardSender(None, 'default')

            self.sender_thread.daemon = True
            self.sender_thread.controller = self
            self.sender_thread.log_command = True

            self.sender_thread.line_sent.connect(self.line_sent_handler)

            if prepend:
                self.logger.debug('Prepend to sender queue')
                self.sender_thread.prepend_commands(commands)
            else:
                self.logger.debug('Append to sender queue')
                self.sender_thread.append_commands(commands)

            self.sender_thread.start()
        else:
            if prepend:
                self.logger.debug('Prepend to existing sender queue')
                self.sender_thread.prepend_commands(commands)
            else:
                self.logger.debug('Append to existing sender queue')
                self.sender_thread.append_commands(commands)

    def control_sender(self, commands):
        # start a new sender or add the new commands to the command queue
        if self.control_sender_thread is None or \
                not self.control_sender_thread.isRunning():
            self.logger.debug('New control sender')
            self.control_sender_thread = ControllerBoardSender(None, 'control')

            self.control_sender_thread.daemon = True
            self.control_sender_thread.controller = self
            self.control_sender_thread.log_command = True

            self.control_sender_thread.line_sent.connect(
                self.line_sent_handler)

            self.logger.debug('Append to control sender queue')
            self.control_sender_thread.append_commands(commands)

            self.control_sender_thread.start()
        else:
            self.logger.debug('Append to existing control sender queue')
            self.control_sender_thread.append_commands(commands)

    def idling_handler(self):
        self.logger.debug('Not listening')
        pub.sendMessage('idling')

    def set_spindle(self, state, speed, direction):
        command = ''

        if state and int(speed) > 0:
            speed = str(speed)

            self.movement_gcode = 'G1'

            if int(direction) == 0:
                command += 'M3 S' + speed
            else:
                command += 'M4 S' + speed

            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (spindle on)'
        else:
            self.movement_gcode = 'G0'
            command += 'M5'
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (spindle off)'

        self.send(command)

    def toggle_coolant(self, state):
        command = ''
        if state:
            command += 'M7\nM8'
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (coolant on)'
        else:
            command += 'M9'
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (coolant off)'

        self.send(command)

    def set_distance_mode(self, mode):
        self.logger.debug('set_distance_mode ' + str(mode))
        command = ''
        if mode == 0:
            command += 'G90'  # absolute
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (absolute)'
        elif mode == 1:
            command += 'G91'  # relative
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (relative)'

        self.send(command)

    def reset_axis(self, axis, position):
        command = 'G92 ' + axis + str(position)

        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (set axis coordinate)'

        self.send(command)

    def set_units(self, metric=True, imperial=False):
        command = ''

        if metric:
            command += 'G21'
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (metric)'
        elif imperial:
            command += 'G20'
            if conf.get('common.add_gcode_comments_for_system_commands'):
                command += ' (imperial)'

        self.send(command)

    def line_received_handler(self, line):
        self.logger.debug('line_received_handler: ' + line)
        line = self.filter_response(str(line).strip())
        log = self.parse_response(line)

        pub.sendMessage('line-received', line=line, log=log)

    def pause_sender(self):
        self.logger.debug('pause_sender')
        if self.sender_thread is not None:
            self.logger.debug('pauseing sender_thread')
            self.sender_thread.pause()

    def resume_sender(self):
        self.logger.debug('resume_sender')
        if self.sender_thread is not None:
            self.logger.debug('resumeing sender_thread')
            self.sender_thread.resume()

    def reset_sender(self):
        self.logger.debug('reset_sender')
        if self.sender_thread is not None:
            self.logger.debug('resetting sender_thread')
            self.sender_thread.reset()

    def pause_timer(self):
        self.logger.debug('pause_timer')
        if self.timer_thread is not None:
            self.logger.debug('pauseing timer_thread')
            self.timer_thread.pause()

    def reset_timer(self):
        if self.timer_thread is not None:
            self.timer_thread.reset()

    def resume_timer(self):
        if self.timer_thread is not None:
            self.timer_thread.resume()

    def line_sent_handler(self, line):
        self.logger.debug('line_sent_handler: ' + line)
        line = self.filter_request(str(line).strip())
        log = self.parse_request(line)
        pub.sendMessage('line-sent', line=line, log=log)

    def send(self, command, prepend=False, control=False):
        self.logger.debug('Sending:' + command)
        if self.listener_thread is None or \
                not self.listener_thread.isRunning():
            self.listener()

        self.logger.debug('Starting sender')
        self.sender(command, prepend, control)

    def filter_file(self, contents):
        # strip blank lines and comments
        contents = re.sub(r' +([MTG])', r'\n\1', contents)
        contents = re.sub(
            r'^(\(|;)[^\)]*\)\s*$',
            '', contents, flags=re.MULTILINE)
        contents = re.sub(r'\n\s*\n', '\n', contents, flags=re.MULTILINE)

        return contents

    def filter_request(self, line):
        self.logger.debug('Filtering request ' + line)

        if conf.get('common.restrict_file_precision') == 1:
            line = line.replace(
                r'([XYZIJKRP])\s*([\-\+\d])(\.(\d{0,4})\d*)?', r'\1\2\4')

        return line

    def parse_distance_mode(self, line):
        # monitor requests to switch the absolute mode flag
        match = re.search(r'^(G9[01])', line, re.IGNORECASE)
        if match is not None:
            self.logger.debug('Switching distance mode')
            groups = match.groups()

            self.absolute = (groups[0] == 'G90')
            pub.sendMessage(
                'dist-mode-received', dist_mode=int(groups[0] != 'G90'))

        return True

    def parse_feed_rate(self, line):
        # monitor requests to change the feed rate
        match = re.search(r'F([\d\.]+)', line, re.IGNORECASE)
        if match is not None:
            self.logger.debug('Switching feed rate')
            groups = match.groups()

            feedrate = re.sub(r'[^\d\.]', '', groups[0])
            pub.sendMessage('feed-rate-sent', rate=feedrate)

            return False

        return True

    def parse_request(self, line):
        self.logger.debug('Parsing request: ' + line)

        log = self.parse_feed_rate(line)

        # turn the coolant on
        match = re.search(r'^M[78]', line)
        if match is not None and \
                not self.main_window.ui.checkBoxCoolant.isChecked():
            self.main_window.ui.checkBoxCoolant.setChecked(True)

        # turn the coolant off
        match = re.search(r'^M9', line)
        if match is not None and \
                self.main_window.ui.checkBoxCoolant.isChecked():
            self.main_window.ui.checkBoxCoolant.setChecked(False)

        # turn the spindle on and set the direction
        match = re.search(r'^M([34])', line)
        if match is not None and \
                not self.main_window.ui.checkBoxSpindle.isChecked():
            groups = match.groups()
            self.main_window.ui.checkBoxSpindle.setChecked(True)
            if groups[0] == '3' and not \
                    self.main_window.ui.radioSpindleDirectionCW.isChecked():
                self.main_window.ui.radioSpindleDirectionCW.setChecked(True)
            elif groups[0] == '4' and not \
                    self.main_window.ui.radioSpindleDirectionCCW.isChecked():
                self.main_window.ui.radioSpindleDirectionCCW.setChecked(True)

        # set or add the spindle speed
        match = re.search(r'^(?:M[34] )?S(\d+)', line)
        if match is not None:
            groups = match.groups()
            speed_index = self.main_window.ui.comboSpindleSpeed.findText(
                groups[0])
            if speed_index < 0:
                self.main_window.ui.comboSpindleSpeed.addItem(groups[0])
            speed_index = self.main_window.ui.comboSpindleSpeed.findText(
                groups[0])
            self.main_window.ui.comboSpindleSpeed.setCurrentIndex(speed_index)

        # turn the spindle off
        match = re.search(r'^M5', line)
        if match is not None and \
                self.main_window.ui.checkBoxSpindle.isChecked():
            self.main_window.ui.checkBoxSpindle.setChecked(False)

        # scan for Gcodes and figure out reverse command
        match = re.search(r'^G(\d+)(.*)', line)
        if match is not None:
            groups = match.groups()
            # if groups[0] == '':

        log = self.parse_distance_mode(line) and log

        session_re = re.compile('_' + self.session_id + '_')
        match = re.search(session_re, line)
        if match is not None:
            log = False

        return log

    def zero_axis(self, axis):
        command = 'G92 ' + axis + '0'
        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (zero axis)'

        self.send(command)

    def progress(self, increment_commands=0):
        if self.number_of_commands == 0:
            return 0

        self.commands_executed += increment_commands
        self.logger.debug(
            'progress: ' + str(self.commands_executed) +
            '/' + str(self.number_of_commands))
        return int(round(
            float(self.commands_executed) /
            float(self.number_of_commands), 2) * 100)

    def clear(self):
        self.logger.debug('controller stopping and clearing')
        self.reset_sender()

    def pause(self):
        self.pause_sender()

    def resume(self):
        self.resume_sender()

    def send_file(self, file_path):
        self.pauseState = False

        pub.sendMessage('programme-progress', progress=0)
        pub.sendMessage('queue-size', size=0)

        content = ''
        with open(file_path) as f:
            content = f.read()

        if bool(conf.get('common.filter_file_commands')):
            content = self.filter_file(content)
            # self.logger.debug('filtered file:' + content)

        if content is not None and content != '':
            self.commands_executed = 0
            self.queue_size = 0
            self.number_of_commands = 0
            self.clear_command_queue()

            # wait for the sender to become ready
            while self.sender_thread is not None and \
                    self.sender_thread.isRunning():
                time.sleep(0.3)

            self.tracking_progress = True
            self.timer()
            self.echo_back('start-of-file')
            self.sender(content)
            self.echo_back('end-of-file')

    def add_tab_to_config(self, ui):
        return None
