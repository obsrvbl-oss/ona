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
from os import remove
from unittest import TestCase
from tempfile import NamedTemporaryFile

from mock import patch

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
        'OBSRVBL_NETFLOW_SERVICE': 'true',
        'OBSRVBL_HOSTNAME_RESOLVER': 'false',
        'OBSRVBL_PNA_IFACES': 'eth0\neth1',
    }

    return D.get(varname, value)


class SupervisorConfigTestCase(TestCase):
    def setUp(self):
        self.infile_path = NamedTemporaryFile(delete=False).name
        self.outfile_path = NamedTemporaryFile(delete=False).name

        with io.open(self.infile_path, mode='wt') as f:
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
            'program:ona-netflow-monitor',
            'program:ona-netflow-pusher',
        ]
        self.assertItemsEqual(actual, expected)

    @patch('ona_service.supervisor_config.getenv', mock_getenv)
    def test_standard_program(self):
        self.inst.update()

        actual = dict(self.inst.config.items('program:ona-netflow-pusher'))

        expected = DEFAULT_PARAMETERS.copy()
        expected['command'] = ' '.join(PROGRAM_COMMANDS['ona-netflow-pusher'])
        expected['stdout_logfile'] = LOG_PATH.format('ona-netflow-pusher')

        self.assertEqual(actual, expected)

    @patch('ona_service.supervisor_config.getenv', mock_getenv)
    def test_custom_program(self):
        self.inst.update()

        actual = dict(self.inst.config.items('program:ona-pna-monitor_eth1'))

        expected = PROGRAM_PARAMETERS['ona-pna-monitor'].copy()
        expected['command'] = ' '.join(
            PROGRAM_COMMANDS['ona-pna-monitor'] + ['eth1']
        )

        self.assertEqual(actual, expected)

    @patch('ona_service.supervisor_config.getenv', mock_getenv)
    def test_write(self):
        self.inst.update()
        self.inst.write()

        new_config = RawConfigParser()
        new_config.read(self.outfile_path)

        actual = new_config.sections()
        expected = self.inst.config.sections()
        self.assertItemsEqual(actual, expected)

        for section in new_config.sections():
            actual = dict(new_config.items(section))
            expected = dict(self.inst.config.items(section))
            self.assertEqual(actual, expected)
