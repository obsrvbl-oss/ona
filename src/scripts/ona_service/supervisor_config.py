#  Copyright 2015 Observable Networks
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import print_function, unicode_literals

import io

from ConfigParser import RawConfigParser
from os import getenv

INFILE_PATH = '/opt/obsrvbl-ona/system/supervisord/ona-supervisord.base'
OUTFILE_PATH = '/opt/obsrvbl-ona/system/supervisord/ona-supervisord.conf'

PYTHON_PATH = '/usr/bin/python2.7'
LOG_PATH = '/opt/obsrvbl-ona/logs/ona_service/{}.log'

DEFAULT_PARAMETERS = {
    'user': 'obsrvbl_ona',
    'directory': '/opt/obsrvbl-ona',
    'autostart': 'true',
    'autorestart': 'true',
    'startretries': '100',
    'stopasgroup': 'true',
    'redirect_stderr': 'true',
    'stdout_logfile_maxbytes': '1MB',
    'stdout_logfile_backups': '0',
}

PROGRAM_PARAMETERS = {
    'ona-pna-monitor': {
        'user': 'obsrvbl_ona',
        'directory': '/opt/obsrvbl-ona',
        'autostart': 'true',
        'autorestart': 'true',
        'startretries': '100',
        'stopasgroup': 'true',
        'stdout_logfile': '/dev/null',
        'stderr_logfile': '/dev/null',
    },
}

PROGRAM_COMMANDS = {
    'ona-service': [
        '/opt/obsrvbl-ona/system/supervisord/ona-service.sh'
    ],
    'ona-hostname-resolver': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/hostname_resolver.py'
    ],
    'ona-log-watcher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/log_watcher.py'
    ],
    'ona-netflow-monitor': [
        '/opt/obsrvbl-ona/netflow/netflow-monitor.sh'
    ],
    'ona-netflow-pusher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/netflow_pusher.py'
    ],
    'ona-notification-publisher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/notification_publisher.py'
    ],
    'ona-ossec-alert-watcher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/ossec_alert_watcher.py'
    ],
    'ona-pna-monitor': [
        '/opt/obsrvbl-ona/system/supervisord/ona-pna-monitor.sh'
    ],
    'ona-pna-pusher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/pna_pusher.py'
    ],
    'ona-arp-capturer': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/arp_capturer.py'
    ],
    'ona-iec61850-capturer': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/iec61850_capturer.py'
    ],
    'ona-pdns-capturer': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/pdns_capturer.py'
    ],
    'ona-suricata-alert-watcher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/suricata_alert_watcher.py'
    ],
    'ona-nmapper': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/nmapper.py'
    ],
}

ENABLE_FLAGS = [
    ('OBSRVBL_NETFLOW_SERVICE', ['ona-netflow-monitor', 'ona-netflow-pusher']),
    ('OBSRVBL_HOSTNAME_RESOLVER', ['ona-hostname-resolver']),
    ('OBSRVBL_NOTIFICATION_PUBLISHER', ['ona-notification-publisher']),
    ('OBSRVBL_ARP_CAPTURER', ['ona-arp-capturer']),
    ('OBSRVBL_IEC61850_CAPTURER', ['ona-iec61850-capturer']),
    ('OBSRVBL_PDNS_CAPTURER', ['ona-pdns-capturer']),
    ('OBSRVBL_SERVICE_OSSEC', ['ona-ossec-alert-watcher']),
    ('OBSRVBL_SERVICE_SURICATA', ['ona-suricata-alert-watcher']),
    ('OBSRVBL_LOG_WATCHER', ['ona-log-watcher']),
    ('OBSRVBL_NMAPPER', ['ona-nmapper']),
]


class SupervisorConfig(object):
    def __init__(self, infile_path=INFILE_PATH, outfile_path=OUTFILE_PATH):
        self.infile_path = infile_path
        self.outfile_path = outfile_path

        self.config = RawConfigParser()
        self.config.read(self.infile_path)

    def add_program(self, service_name, extra_args=None):
        extra_args = [] if extra_args is None else extra_args[:]

        section_name = 'program:{}'.format(service_name)
        if extra_args:
            section_name = '{}_{}'.format(section_name, '-'.join(extra_args))
        self.config.add_section(section_name)

        command_args = PROGRAM_COMMANDS[service_name] + extra_args
        command_string = ' '.join(command_args)
        self.config.set(section_name, 'command', command_string)

        if service_name in PROGRAM_PARAMETERS:
            for key, value in PROGRAM_PARAMETERS[service_name].iteritems():
                self.config.set(section_name, key, value)
        else:
            for key, value in DEFAULT_PARAMETERS.iteritems():
                self.config.set(section_name, key, value)
            self.config.set(
                section_name, 'stdout_logfile', LOG_PATH.format(service_name)
            )

    def update(self):
        # PNA services (one monitor per interface and one pusher)
        if getenv('OBSRVBL_PNA_SERVICE', 'false') == 'true':
            for iface in getenv('OBSRVBL_PNA_IFACES', '').split():
                self.add_program('ona-pna-monitor', extra_args=[iface])
            self.add_program('ona-pna-pusher')

        # All other services
        for flag, program_list in ENABLE_FLAGS:
            if getenv(flag, 'false') != 'true':
                continue
            for program in program_list:
                self.add_program(program)

    def write(self):
        with io.open(self.outfile_path, 'wb') as outfile:
            self.config.write(outfile)


if __name__ == '__main__':
    supervisor_config = SupervisorConfig()
    supervisor_config.update()
    supervisor_config.write()
