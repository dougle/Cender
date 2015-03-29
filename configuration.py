import os.path
import logging
import serial
from configobj import ConfigObj
import collections


class Config():

    boolean_elements = [
        'common.add_gcode_comments_for_system_commands',
        'ui.disable_homing',
        'common.auto_connect',
        'common.filter_file_commands',
        'common.restrict_file_precision',
        'common.check_firmware_version']
    configobj = ConfigObj()

    def __init__(self):
        self.config_filename = 'current.conf'
        self.logger = logging.getLogger(__name__)
        self.configobj = ConfigObj(self.config_filename)

        if not os.path.isfile(self.config_filename):
            self.configobj = self.generate_default()
            self.configobj.write()

            self.logger.debug('Default configuration loaded')
        else:
            self.logger.debug(
                'Configuration file ' + self.config_filename + ' loaded')

    def generate_default(self):
        default_config = ConfigObj(self.config_filename)
        default_config['common'] = {}
        default_config['connection'] = {}
        default_config['connection']['port'] = {}
        default_config['ui'] = {}

        default_config['common']['log_level'] = 0
        default_config['common'][
            'add_gcode_comments_for_system_commands'] = True
        default_config['common']['board_type'] = 'TinyG 0.97'
        default_config['common']['minimum_spindle_speed'] = 5000
        default_config['common']['auto_connect'] = False
        default_config['common']['directory'] = os.path.expanduser("~")
        default_config['common']['units'] = 0
        default_config['common']['filter_file_commands'] = True
        default_config['common']['restrict_file_precision'] = True
        default_config['common']['check_firmware_version'] = True

        default_config['connection']['port'] = {}
        default_config['connection']['port']['name'] = "/dev/ttyUSB0"
        default_config['connection']['port']['baud'] = 115200
        default_config['connection']['port']['read_timeout'] = 0
        default_config['connection']['port']['write_timeout'] = 0
        default_config['connection']['port']['stopbits'] = serial.STOPBITS_ONE
        default_config['connection']['port']['parity'] = 'None'
        default_config['connection']['port']['flow_control'] = 'rtscts'

        default_config['ui']['spindle_speed_index'] = 0
        default_config['ui']['show_visualiser'] = False
        default_config['ui']['jog_step_index'] = 3
        default_config['ui']['feed_rate_index'] = 4
        default_config['ui']['spindle_direction'] = 0
        default_config['ui']['disable_homing'] = False
        default_config['ui']['lcd_precision'] = 3
        default_config['ui']['offset_names'] = [
            'Work Offset 1', 'Work Offset 2', 'Work Offset 3']
        default_config['ui']['current_offset_index'] = 0
        default_config['ui']['offsets'] = {}

        return default_config

    def get(self, path):
        # self.logger.debug('Get config item '+ path)
        value = self.fetch_value_via_path(self.configobj, path)

        # fetch a default config value and merge it with the existing config
        if value is None:
            value = self.fetch_value_via_path(self.generate_default(), path)
            # self.logger.debug('     default to '+ value)
            if value is not None:
                self.set(path, value)

        return value

    def build_temp_config_dictionary(self, keys, value):
        keys.reverse()
        try:
            this_key = keys.pop()
        except IndexError:
            return value

        keys.reverse()
        # recurse
        frag = {}
        frag[this_key] = {}
        frag[this_key] = self.build_temp_config_dictionary(keys, value)

        return frag

    def set(self, path, value):
        keys = path.split('.')
        temp_config = self.build_temp_config_dictionary(keys, value)

        self.configobj.merge(temp_config)
        self.configobj.write()
        self.configobj.reload()

    def fetch_value_via_path(self, list, path):
        keys = path.split('.')
        current_element = list
        for key in keys:
            if key in current_element:
                current_element = current_element[key]
            else:
                return None

        try:
            if self.boolean_elements.index(path) >= 0:
                current_element = (current_element == 'True')
        except:
            pass

        return current_element

    def save_to_file(self, abs_file_path):
        abs_file_path = str(abs_file_path)

        cwd = os.getcwd()
        os.chdir(os.path.dirname(abs_file_path))
        config_clone = ConfigObj(os.path.basename(abs_file_path))
        config_clone.merge(self.configobj)
        config_clone.write()
        os.chdir(cwd)

    def load_from_file(self, abs_file_path):
        abs_file_path = str(abs_file_path)

        cwd = os.getcwd()
        os.chdir(os.path.dirname(abs_file_path))
        config_clone = ConfigObj(os.path.basename(abs_file_path))
        self.configobj.merge(config_clone)
        os.chdir(cwd)

        self.configobj.write()
        self.configobj.reload()


conf = Config()
