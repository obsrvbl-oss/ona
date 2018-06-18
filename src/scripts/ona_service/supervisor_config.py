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

from flowcap_config import ENV_YAF_START_PORT, DEFAULT_YAF_START_PORT

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
    'ona-pdns-monitor': [
        '/opt/obsrvbl-ona/system/supervisord/ona-pdns-monitor.sh'
    ],
    'ona-pdns-pusher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/pdns_pusher.py'
    ],
    'ona-suricata-alert-watcher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/suricata_alert_watcher.py'
    ],
    'ona-nmapper': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/nmapper.py'
    ],
    'ona-share-watcher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/share_watcher.py'
    ],
    'ona-ipfix-pusher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/ipfix_pusher.py'
    ],
    'ona-ipfix-monitor': [
        '/opt/obsrvbl-ona/ipfix/flowcap.sh'
    ],
    'ona-yaf-monitor': [
        '/opt/obsrvbl-ona/system/supervisord/ona-yaf-monitor.sh'
    ],
    'ona-syslog-ad-watcher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/syslog_ad_watcher.py'
    ],
    'ona-check-point-pusher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/check_point_pusher.py'
    ],
    'ona-eta-monitor': [
        '/opt/obsrvbl-ona/system/supervisord/ona-eta-monitor.sh'
    ],
    'ona-eta-pusher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/eta_pusher.py'
    ],
    'ona-nvzflow-monitor': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/nvzflow_reader.py'
    ],
    'ona-nvzflow-pusher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/nvzflow_pusher.py'
    ],
    'ona-kubernetes-watcher': [
        PYTHON_PATH, '/opt/obsrvbl-ona/ona_service/kubernetes_watcher.py'
    ],
}

ENABLE_FLAGS = [
    ('OBSRVBL_HOSTNAME_RESOLVER', ['ona-hostname-resolver']),
    ('OBSRVBL_NOTIFICATION_PUBLISHER', ['ona-notification-publisher']),
    ('OBSRVBL_PDNS_CAPTURER', ['ona-pdns-monitor', 'ona-pdns-pusher']),
    ('OBSRVBL_SERVICE_OSSEC', ['ona-ossec-alert-watcher']),
    ('OBSRVBL_SERVICE_SURICATA', ['ona-suricata-alert-watcher']),
    ('OBSRVBL_LOG_WATCHER', ['ona-log-watcher']),
    ('OBSRVBL_NMAPPER', ['ona-nmapper']),
    ('OBSRVBL_SHARE_WATCHER', ['ona-share-watcher']),
    ('OBSRVBL_IPFIX_CAPTURER', ['ona-ipfix-monitor', 'ona-ipfix-pusher']),
    ('OBSRVBL_SYSLOG_AD_WATCHER', ['ona-syslog-ad-watcher']),
    ('OBSRVBL_CHECK_POINT_PUSHER', ['ona-check-point-pusher']),
    ('OBSRVBL_KUBERNETES_WATCHER', ['ona-kubernetes-watcher']),
    ('OBSRVBL_ETA_CAPTURER', ['ona-eta-monitor', 'ona-eta-pusher']),
    (
        'OBSRVBL_NVZFLOW_CAPTURER',
        ['ona-nvzflow-monitor', 'ona-nvzflow-pusher']
    ),
]


class SupervisorConfig(object):
    def __init__(self, infile_path=INFILE_PATH, outfile_path=OUTFILE_PATH):
        self.infile_path = infile_path
        self.outfile_path = outfile_path

        self.config = RawConfigParser()
        self.config.read(self.infile_path)
        self.program_set = set()

    def add_program(self, service_name, extra_args=None):
        # Ensure that duplicate programs do not get added
        extra_args = [] if extra_args is None else extra_args[:]
        if (service_name, tuple(extra_args)) in self.program_set:
            return
        self.program_set.add((service_name, tuple(extra_args)))

        section_name = 'program:{}'.format(service_name)
        if extra_args:
            section_name = '{}_{}'.format(section_name, '-'.join(extra_args))
        self.config.add_section(section_name)

        command_args = PROGRAM_COMMANDS[service_name] + extra_args
        command_string = ' '.join('"{}"'.format(x) for x in command_args)
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
        # Interfaces for PNA and YAF
        all_ifaces = sorted(getenv('OBSRVBL_PNA_IFACES', '').split())

        # PNA services (one monitor per interface and one pusher)
        if getenv('OBSRVBL_PNA_SERVICE', 'false') == 'true':
            for iface in all_ifaces:
                self.add_program('ona-pna-monitor', extra_args=[iface])
            self.add_program('ona-pna-pusher')

        # YAF services (one monitor per interface, one IPFIX receiver, and one
        # pusher)
        if getenv('OBSRVBL_YAF_CAPTURER', 'false') == 'true':
            self.add_program('ona-ipfix-monitor')

            yaf_start_port = int(
                getenv(ENV_YAF_START_PORT, DEFAULT_YAF_START_PORT)
            )
            for i, iface in enumerate(all_ifaces):
                yaf_port = '{}'.format(yaf_start_port + i)
                self.add_program(
                    'ona-yaf-monitor', extra_args=[iface, yaf_port]
                )
            self.add_program('ona-ipfix-pusher')

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
