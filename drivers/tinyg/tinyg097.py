import logging
import re
from configuration import conf
from tinyg import TinyG
from pubsub import pub


class TinyG097(TinyG):

    def parse_queue_report(self, response):
        # check queue report and set/clear flag to send
        if 'qr' in response and 'qi' in response and 'qo' in response:
            free_queue_slots = min(
                self.command_queue_slots, int(response['qr']))
            queue_size = (self.command_queue_slots - free_queue_slots)
            self.logger.debug('queue_size: ' + str(queue_size))

            if self.tracking_progress and response['qo'] != '0':
                pub.sendMessage(
                    'programme-progress',
                    progress=self.progress(int(response['qo'])))

            pub.sendMessage('queue-size', size=queue_size)

            return False

        # check for min move error, in which case command skipped
        if 'err' in response and \
                response['err'] == 'Move less than minimum length':
            if self.tracking_progress:
                pub.sendMessage(
                    'programme-progress', progress=self.progress(1))
            return False

        return True

    def enable_queue_reports(self):
        command = '$qv=2'
        if conf.get('common.add_gcode_comments_for_system_commands'):
            command += ' (enable verbose queue reports)'
        self.send(command)

    def request_command_queue_size(self):
        self.logger.debug('requesting queue size')
        # self.send('$qr')

        return None
