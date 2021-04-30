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
from logging import getLogger
from unittest import TestCase
from unittest.mock import patch

from ona_service.snmp_handler import SnmpHandler


TEST_PORT = 13456


class SnmpHandlerTest(TestCase):
    def setUp(self):
        self.logger = getLogger('testing')
        self.logger.handlers = []

    @patch('ona_service.snmp_handler.subprocess.call')
    def test_defaults(self, mock_cmd):
        handler = SnmpHandler('user', '1.3.6.1.4.1.3375.2.100')
        self.logger.addHandler(handler)

        self.logger.error("onoes!")

        self.assertEquals(len(mock_cmd.call_args_list), 1)
        self.assertEquals(mock_cmd.call_args_list[0][0][0], [
            'snmptrap',
            '-v', '2c',
            '-c', 'user',
            'localhost:162',
            "''",  # empty for uptime
            '.1.3.6.1.4.1.3375.2.100',
            '.1.3.6.1.4.1.3375.2.100.0', 's', "'onoes!'",
        ])

    @patch('ona_service.snmp_handler.subprocess.call')
    def test_wont_log_warning(self, mock_cmd):
        handler = SnmpHandler('user', '1.3.6.1.4.1.3375.2.100')
        self.logger.addHandler(handler)

        self.logger.warn("onoes!")
        self.logger.warn("what!!")
        self.logger.warn("huh?")

        self.assertEquals(len(mock_cmd.call_args_list), 0)

    @patch('ona_service.snmp_handler.subprocess.call')
    def test_v2_params(self, mock_cmd):
        handler = SnmpHandler('user1', '1.3.6.1.4.1.3375.2.100',
                              host='127.0.0.1', port='9001')
        self.logger.addHandler(handler)

        self.logger.error('{"hello, my name is json": true}')

        self.assertEquals(len(mock_cmd.call_args_list), 1)
        self.assertEquals(mock_cmd.call_args_list[0][0][0], [
            'snmptrap',
            '-v', '2c',
            '-c', 'user1',
            '127.0.0.1:9001',
            "''",  # empty for uptime
            '.1.3.6.1.4.1.3375.2.100',
            '.1.3.6.1.4.1.3375.2.100.0', 's',
            "'{\"hello, my name is json\": true}'",
        ])

    @patch('ona_service.snmp_handler.subprocess.call')
    def test_v3_params(self, mock_cmd):
        handler = SnmpHandler('user1', '1.3.6.1.4.1.3375.2.100',
                              version='3', host='127.0.0.1', port='9001',
                              passcode='passcode1', engineID='0607080910',
                              authentication='MD5')
        self.logger.addHandler(handler)

        self.logger.error('{"hello, my name is json": true}')

        self.assertEquals(len(mock_cmd.call_args_list), 1)
        self.assertEquals(mock_cmd.call_args_list[0][0][0], [
            'snmptrap',
            '-v', '3',
            '-e', '0x0607080910',
            '-u', 'user1',
            '-a', 'MD5',
            '-x', 'AES',
            '-A', 'passcode1',
            '-l', 'authNoPriv',
            '127.0.0.1:9001',
            "''",  # empty for uptime
            '.1.3.6.1.4.1.3375.2.100',
            '.1.3.6.1.4.1.3375.2.100.0', 's',
            "'{\"hello, my name is json\": true}'",
        ])
