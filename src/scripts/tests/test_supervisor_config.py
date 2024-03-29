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
from configparser import RawConfigParser
from os import remove
from unittest import TestCase
from unittest.mock import patch
from tempfile import NamedTemporaryFile

from ona_service.supervisor_config import (
    DEFAULT_PARAMETERS,
    LOG_PATH,
    PROGRAM_COMMANDS,
    PROGRAM_PARAMETERS,
    SupervisorConfig,
)

INFILE_CONTENTS = """\
[supervisord]
logfile=/tmp/ona-supervisord.log
pidfile=/tmp/ona-supervisord.pid
nodaemon=false
user=obsrvbl_ona
logfile_maxbytes=1MB
logfile_backups=0
"""


def mock_getenv(varname, value=None):
    D = {
        'OBSRVBL_PNA_SERVICE': 'true',
        'OBSRVBL_HOSTNAME_RESOLVER': 'false',
        'OBSRVBL_NOTIFICATION_PUBLISHER': 'true',
        'OBSRVBL_PNA_IFACES': 'eth0\neth1',
        'OBSRVBL_YAF_CAPTURER': 'true',
        'OBSRVBL_IPFIX_CAPTURER': 'true',
        'OBSRVBL_PDNS_CAPTURER': 'true',
    }

    return D.get(varname, value)


class SupervisorConfigTestCase(TestCase):
    def setUp(self):
        self.infile_path = NamedTemporaryFile(delete=False).name
        self.outfile_path = NamedTemporaryFile(delete=False).name

        with open(self.infile_path, mode='wt') as f:
            f.write(INFILE_CONTENTS)

        self.inst = SupervisorConfig(
            infile_path=self.infile_path, outfile_path=self.outfile_path
        )

    def tearDown(self):
        remove(self.infile_path)
        remove(self.outfile_path)

    @patch('ona_service.supervisor_config.getenv', mock_getenv)
    def test_sections(self):
        self.inst.update()
        actual = self.inst.config.sections()
        expected = [
            'supervisord',
            'program:ona-pna-monitor_eth0',
            'program:ona-pna-monitor_eth1',
            'program:ona-pna-pusher',
            'program:ona-ipfix-monitor',
            'program:ona-yaf-monitor_eth0-4739',
            'program:ona-yaf-monitor_eth1-4740',
            'program:ona-ipfix-pusher',
            'program:ona-notification-publisher',
            'program:ona-pdns-monitor',
            'program:ona-pdns-pusher',
        ]
        self.assertCountEqual(actual, expected)

    @patch('ona_service.supervisor_config.getenv', mock_getenv)
    def test_standard_program(self):
        self.inst.update()

        actual = dict(
            self.inst.config.items('program:ona-notification-publisher')
        )

        expected = DEFAULT_PARAMETERS.copy()
        args = PROGRAM_COMMANDS['ona-notification-publisher']
        expected['command'] = ' '.join('"{}"'.format(x) for x in args)
        expected['stdout_logfile'] = LOG_PATH.format(
            'ona-notification-publisher'
        )

        self.assertEqual(actual, expected)

    @patch('ona_service.supervisor_config.getenv', mock_getenv)
    def test_pna(self):
        self.inst.update()

        actual = dict(self.inst.config.items('program:ona-pna-monitor_eth1'))

        expected = PROGRAM_PARAMETERS['ona-pna-monitor'].copy()
        args = PROGRAM_COMMANDS['ona-pna-monitor'] + ['eth1']
        expected['command'] = ' '.join('"{}"'.format(x) for x in args)

        self.assertEqual(actual, expected)

    @patch('ona_service.supervisor_config.getenv', mock_getenv)
    def test_yaf(self):
        self.inst.update()

        actual = dict(
            self.inst.config.items('program:ona-yaf-monitor_eth1-4740')
        )

        expected = DEFAULT_PARAMETERS.copy()
        args = PROGRAM_COMMANDS['ona-yaf-monitor'] + ['eth1', '4740']
        expected['command'] = ' '.join('"{}"'.format(x) for x in args)
        expected['stdout_logfile'] = LOG_PATH.format('ona-yaf-monitor')

        self.assertEqual(actual, expected)

    @patch('ona_service.supervisor_config.getenv', mock_getenv)
    def test_write(self):
        self.inst.update()
        self.inst.write()

        new_config = RawConfigParser()
        new_config.read(self.outfile_path)

        actual = new_config.sections()
        expected = self.inst.config.sections()
        self.assertCountEqual(actual, expected)

        for section in new_config.sections():
            actual = dict(new_config.items(section))
            expected = dict(self.inst.config.items(section))
            self.assertEqual(actual, expected)
