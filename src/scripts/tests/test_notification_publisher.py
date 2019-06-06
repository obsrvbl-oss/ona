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
import socket

from binascii import unhexlify
from datetime import datetime
from json import dumps
from os.path import join
from shutil import rmtree
from tempfile import mkdtemp
from time import time
from unittest import TestCase

from mock import call, patch, MagicMock
from requests import Response

from ona_service.notification_publisher import (
    ENV_NOTIFICATION_TYPES,
    NotificationPublisher,
    STATE_FILE,
    POST_PUBLISH_WAIT_SECONDS,
)
from ona_service.utils import utc, utcnow

PATCH_PATH = 'ona_service.notification_publisher.{}'.format

RESPONSE_OBJECTS = [
    {'time': '2018-09-28T00:10:00+00:00'},
    {'time': '2018-09-28T00:11:00+00:00'},
]


class NotificationPublisherTests(TestCase):
    def setUp(self):
        self.temp_dir = mkdtemp()

    def tearDown(self):
        rmtree(self.temp_dir, ignore_errors=True)

    def _get_instance(self, **environment):
        with patch.dict(PATCH_PATH('os_environ'), environment):
            state_file_path = join(self.temp_dir, STATE_FILE)
            with patch(PATCH_PATH('STATE_FILE'), state_file_path):
                inst = NotificationPublisher()
                inst.api = MagicMock(inst.api)

        return inst

    def _get_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)
        sock.bind(('localhost', 0))
        host, port = sock.getsockname()

        return sock, host, port

    def test_get_data(self):
        # When all is well, the get_data method returns the deserialized
        # objects
        inst = self._get_instance()

        response = Response()
        response.status_code = 200
        response._content = dumps({'objects': RESPONSE_OBJECTS})
        inst.api.get_data.return_value = response

        params = {'time__gt': '2018-09-28T00:00:00+00:00'}
        actual = inst.get_data('alerts', params)
        self.assertEqual(actual, RESPONSE_OBJECTS)

    def test_get_data_server_error(self):
        # If there's an error and no JSON is returned, the get_data method
        # returns None
        inst = self._get_instance()

        response = Response()
        response.status_code = 500
        response._content = b'No go, bro'
        inst.api.get_data.return_value = response

        params = {'time__gt': '2018-09-28T00:00:00+00:00'}
        actual = inst.get_data('alerts', params)
        self.assertIsNone(actual)

    def test_get_data_client_error(self):
        # When all is well, the get_data method returns the deserialized
        # objects
        inst = self._get_instance()

        response = Response()
        response.status_code = 400
        data = {
            'error': 'What were you trying to do?'
        }
        response._content = dumps(data)
        inst.api.get_data.return_value = response

        params = {'time__gt': '2018-09-28T00:00:00+00:00'}
        actual = inst.get_data('alerts', params)
        self.assertIsNone(actual)

    def test_publish_wait(self):
        # We should wait a bit in between messages - not send them all at once
        inst = self._get_instance()
        inst.logger = MagicMock()

        messages = ['message_1', 'message_2', 'message_3']
        start_time = time()
        inst.publish(messages, 'info')
        end_time = time()

        self.assertEqual(
            inst.logger.info.mock_calls, [call(x) for x in messages]
        )

        elapsed = end_time - start_time
        min_elapsed = POST_PUBLISH_WAIT_SECONDS * len(messages)
        self.assertGreater(elapsed, min_elapsed)

    def test_publish_error(self):
        # Even if there's an error in publishing, we should attempt to publish
        # all messages
        inst = self._get_instance()
        inst.logger = MagicMock()
        inst.logger.info.side_effect = ValueError

        messages = ['message_1', 'message_2']
        inst.publish(messages, 'info')
        self.assertEqual(
            inst.logger.info.mock_calls, [call(x) for x in messages]
        )

    def test_execute_no_handlers(self):
        # Nothing enabled means no calls to the API
        inst = self._get_instance()
        inst.execute()
        self.assertEqual(len(inst.api.mock_calls), 0)

    def test_execute_bad_data_type(self):
        # Users can specify incorrect data types; don't crash
        environment = {
            ENV_NOTIFICATION_TYPES: 'bogus-type',
        }
        inst = self._get_instance(**environment)
        inst.logger = MagicMock()
        inst.execute()
        self.assertEqual(len(inst.api.mock_calls), 0)

    def test_execute_no_state(self):
        # Response data
        response = Response()
        response.status_code = 200
        response._content = dumps({'objects': RESPONSE_OBJECTS})

        inst = self._get_instance()
        inst.api.get_data.return_value = response
        inst.logger = MagicMock()

        inst.execute()

        # By default alerts are published with the "error" priority
        # Observations are also published by default, with "info" priority
        for log_func in (inst.logger.error, inst.logger.info):
            self.assertEqual(
                log_func.mock_calls, [call(x) for x in RESPONSE_OBJECTS]
            )

        # The state file should be filled in with the max time for each type
        for data_type in ('alerts', 'observations'):
            self.assertEqual(
                inst.state[data_type],
                {'time__gt': '2018-09-28T00:11:00+00:00'}
            )

    def test_execute_no_messages(self):
        # Empty response data - no publish attempts should happen
        response = Response()
        response.status_code = 200
        response._content = dumps({'objects': []})

        inst = self._get_instance()
        inst.api.get_data.return_value = response
        inst.logger = MagicMock()

        now = utcnow().replace(tzinfo=utc)
        inst.execute(now=now)

        self.assertEqual(inst.logger.error.call_count, 0)
        self.assertEqual(inst.logger.info.call_count, 0)

        # The state file should be filled in with the call time, even though
        # there were no messages
        for data_type in ('alerts', 'observations'):
            actual_dt = inst.state[data_type]['time__gt']
            expected_dt = now.isoformat()
            self.assertGreaterEqual(actual_dt, expected_dt)

    def test_execute_syslog(self):
        # Enable syslog and listen for the UDP packets locally
        sock, host, port = self._get_socket()

        # Response data
        response = Response()
        response.status_code = 200
        response._content = dumps({'objects': RESPONSE_OBJECTS})

        environment = {
            'OBSRVBL_SYSLOG_ENABLED': 'true',
            'OBSRVBL_SYSLOG_SERVER': host,
            'OBSRVBL_SYSLOG_SERVER_PORT': str(port),
            'OBSRVBL_SYSLOG_FACILITY': 'local0',
            ENV_NOTIFICATION_TYPES: 'alerts-detail',
        }
        inst = self._get_instance(**environment)
        inst.api.get_data.return_value = response
        inst.execute()
        try:
            messages = [sock.recvfrom(4096)[0] for x in RESPONSE_OBJECTS]
        except socket.timeout:
            self.fail('No message')
        finally:
            sock.close()

        for msg, obj in zip(messages, RESPONSE_OBJECTS):
            dt, hostname, service, level, payload = msg.split(' ', 4)
            datetime.strptime(dt, '<131>%Y-%m-%dT%H:%M:%S.%f+00:00')
            self.assertEqual(service, 'OBSRVBL')
            self.assertEqual(level, '[local0.ERROR]')
            self.assertEqual(payload, '{}\x00'.format(obj))

    def test_execute_snmp(self):
        # Enable SNMP and listen for the UDP packets locally
        sock, host, port = self._get_socket()

        # Response data
        response = Response()
        response.status_code = 200
        response._content = dumps({'objects': RESPONSE_OBJECTS})

        environment = {
            'OBSRVBL_SNMP_ENABLED': 'true',
            'OBSRVBL_SNMP_OBJECTID': '1.3.6.1.4.1.3375.2.100',
            'OBSRVBL_SNMP_SERVER': host,
            'OBSRVBL_SNMP_SERVER_PORT': str(port),
            'OBSRVBL_SNMP_USER': 'yolo',
            ENV_NOTIFICATION_TYPES: 'alerts-detail',
        }
        inst = self._get_instance(**environment)
        inst.api.get_data.return_value = response
        inst.execute()
        try:
            messages = [sock.recvfrom(4096)[0] for x in RESPONSE_OBJECTS]
        except socket.timeout:
            self.fail('No message')
        finally:
            sock.close()

        for msg, obj in zip(messages, RESPONSE_OBJECTS):
            # SNMPv2 is 0x01, of course
            self.assertEqual('\x01', msg[4])
            # Community string
            self.assertIn(b'yolo', msg)
            # OID should be included twice - once to say it's coming, once
            # to give the value
            encoded_oid = unhexlify('2b060104019a2f0264')
            self.assertTrue(msg.count(encoded_oid), 2)
            # Encoded message should appear
            self.assertIn(str(obj), msg)

    def test_execute_snmpv3(self):
        # Enable SNMPv3 and listen for the UDP packets locally
        sock, host, port = self._get_socket()

        # Response data
        response = Response()
        response.status_code = 200
        response._content = dumps({'objects': RESPONSE_OBJECTS})

        environment = {
            'OBSRVBL_SNMP_ENABLED': 'true',
            'OBSRVBL_SNMP_OBJECTID': '1.3.6.1.4.1.3375.2.100',
            'OBSRVBL_SNMP_SERVER': host,
            'OBSRVBL_SNMP_SERVER_PORT': str(port),
            'OBSRVBL_SNMP_VERSION': '3',
            'OBSRVBL_SNMPV3_ENGINEID': '0102030405',
            'OBSRVBL_SNMPV3_PASSPHRASE': 'opensesame',
            'OBSRVBL_SNMP_USER': 'nolo',
            ENV_NOTIFICATION_TYPES: 'alerts-detail',
        }
        inst = self._get_instance(**environment)
        inst.api.get_data.return_value = response
        inst.execute()
        try:
            messages = [sock.recvfrom(4096)[0] for x in RESPONSE_OBJECTS]
        except socket.timeout:
            self.fail('No message')
        finally:
            sock.close()

        for msg, obj in zip(messages, RESPONSE_OBJECTS):
            # SNMPv3 is 0x03, which does make sense
            self.assertEqual('\x03', msg[5])
            # User is in the message
            self.assertIn(b'nolo', msg)
            # OID should be included twice - once to say it's coming, once
            # to give the value
            encoded_oid = unhexlify('2b060104019a2f0264')
            self.assertTrue(msg.count(encoded_oid), 2)
            # Encoded message should appear
            self.assertIn(str(obj), msg)
