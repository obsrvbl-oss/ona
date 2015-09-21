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
import json
import logging
import os
import re
import signal
import socket

from datetime import datetime
from shutil import rmtree
from tempfile import mkdtemp
from threading import Thread, Condition
from time import time
from unittest import TestCase

from mock import call, patch, Mock

from ona_service.notification_publisher import (
    NotificationPublisher,
    STATE_FILE,
    CONFIG_DEFAULTS,
)
from ona_service.snmp_handler import SnmpHandler
from ona_service.utils import utc

TEST_PORT = 13456


class UdpReceiver(Thread):
    """Thread which can receive UDP messages on a port, so we can make sure
       syslog/snmp is working."""
    def __init__(self, port):
        Thread.__init__(self)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = ("127.0.0.1", port)
        self.socket.bind(self.addr)
        self.packets = []
        self.packets_cv = Condition()

    def run(self):
        self.running = True
        while self.running:
            data, _ = self.socket.recvfrom(4096)

            with self.packets_cv:
                self.packets.append(data)
                self.packets_cv.notify_all()

    def pop(self, timeout_seconds=10):
        """Blocking call that returns the next UDP packet received or
           raises an exception on timeout."""
        start_time = time()

        with self.packets_cv:
            while len(self.packets) == 0:
                total_wait = time() - start_time
                if total_wait < timeout_seconds:
                    self.packets_cv.wait(timeout_seconds)
                else:
                    raise StandardError("Timed out waiting for packet.")

            return self.packets.pop(0)

    def stop(self):
        self.running = False
        self.socket.sendto("quit", self.addr)  # Send jibberish so recv wakes.

    def close(self):
        self.socket.close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        self.stop()
        self.join()
        self.close()


def get_syslog_string(time, facility, priority, message):
    syslog_handler = logging.handlers.SysLogHandler()
    encoded_priority = syslog_handler.encodePriority(facility, priority)
    encoded_message = CONFIG_DEFAULTS['syslog_format'].format(
        time=time,
        sensor_hostname=socket.gethostname(),
        facility=facility,
        priority=priority.upper(),
        message=message,
    )
    return "<%i>%s\000" % (encoded_priority, encoded_message)


class NotificationPublisherTest(TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp_dir = mkdtemp()
        os.chdir(self.tmp_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        rmtree(self.tmp_dir)

    @patch('ona_service.api.Api.get_data', autospec=True)
    def test_get_data(self, mock_get):
        messages = [
            {'id': 1, 'time': '2015-05-01T01:02:03+00:00'},
            {'id': 2, 'time': '2015-05-01T01:02:04+00:00'},
            {'id': 3, 'time': '2015-05-01T01:02:05+00:00'},
        ]
        mock_get.return_value.json.return_value = {'objects': messages}

        pub = NotificationPublisher()
        actual = pub.get_data('thingy', 'params')

        self.assertEquals(actual, messages)
        self.assertEquals(mock_get.call_args_list, [
            call(pub.api, 'thingy', 'params'),
        ])

    @patch('ona_service.api.Api.get_data', autospec=True)
    def test_get_data_kaboom(self, mock_get):
        mock_get.side_effect = ValueError

        pub = NotificationPublisher()
        actual = pub.get_data('thingy', 'params')

        self.assertEquals(actual, None)
        self.assertEquals(mock_get.call_args_list, [
            call(pub.api, 'thingy', 'params'),
        ])

    @patch('ona_service.api.Api.get_data', autospec=True)
    def test_get_data_kerpow(self, mock_get):
        mock_get.return_value.json.return_value = {'error': ':('}

        pub = NotificationPublisher()
        actual = pub.get_data('thingy', 'params')

        self.assertEquals(actual, None)
        self.assertEquals(mock_get.call_args_list, [
            call(pub.api, 'thingy', 'params'),
        ])

    @patch('ona_service.notification_publisher.create_logger', autospec=True)
    def test_publish(self, mock_create_logger):
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger

        pub = NotificationPublisher()

        messages = ['foo', 'bar']
        pub.publish(messages, 'error')
        self.assertEquals(mock_logger.error.call_args_list, [
            call('foo'),
            call('bar'),
        ])

        messages = ['what?']
        pub.publish(messages, 'info')
        self.assertEquals(mock_logger.info.call_args_list, [
            call('what?'),
        ])

        pub.publish([], 'nope')
        self.assertEquals(mock_logger.nope.call_args_list, [])

    def test_publish_syslog(self):
        with UdpReceiver(TEST_PORT) as server:
            with patch.dict('os.environ'):
                os.environ['OBSRVBL_SYSLOG_ENABLED'] = 'True'
                os.environ['OBSRVBL_SYSLOG_SERVER'] = 'localhost'
                os.environ['OBSRVBL_SYSLOG_SERVER_PORT'] = str(TEST_PORT)
                os.environ['OBSRVBL_SYSLOG_FACILITY'] = 'user'

                pub = NotificationPublisher()

                messages = []
                messages.append('foobar')
                pub.publish(messages, 'error')

            msg = server.pop()
            # expect timestamp of the form:
            time = re.search(">(\d+-\d+-\d+T\d+:\d+:\d+.\d+\+00:00)",
                             msg).groups()[0]
            self.assertEqual(
                msg, get_syslog_string(time, 'user', 'error', 'foobar'))

    @patch('ona_service.notification_publisher.SnmpHandler', autospec=True)
    def test_publish_snmp(self, mock_snmp):
        mock_snmp.return_value = SnmpHandler('user', '1.3.6.1.4.1.3375.2.100',
                                             port=TEST_PORT)
        with UdpReceiver(TEST_PORT) as server:
            with patch.dict('os.environ'):
                os.environ['OBSRVBL_SNMP_ENABLED'] = 'True'
                os.environ['OBSRVBL_SNMP_OBJECTID'] = '1.3.6.1.4.1.3375.2.100'
                os.environ['OBSRVBL_SNMP_SERVER'] = 'localhost'
                os.environ['OBSRVBL_SNMP_USER'] = 'user'

                pub = NotificationPublisher()

                messages = []
                messages.append('foobar')
                pub.publish(messages, 'error')

            msg = server.pop()
            self.assertRegexpMatches(msg, 'foobar')

        self.assertEquals(mock_snmp.call_args_list, [
            call(objectID='1.3.6.1.4.1.3375.2.100', port=162, host='localhost',
                 user='user', version='2c', passcode=None, engineID=None),
        ])

    @patch('ona_service.notification_publisher.SnmpHandler', autospec=True)
    def test_publish_snmpv3(self, mock_snmp):
        mock_snmp.return_value = SnmpHandler('user', '1.3.6.1.4.1.3375.2.100',
                                             port=TEST_PORT)
        with UdpReceiver(TEST_PORT) as server:
            with patch.dict('os.environ'):
                os.environ['OBSRVBL_SNMP_ENABLED'] = 'True'
                os.environ['OBSRVBL_SNMP_OBJECTID'] = '1.3.6.1.4.1.3375.2.100'
                os.environ['OBSRVBL_SNMP_SERVER'] = 'localhost'
                os.environ['OBSRVBL_SNMP_USER'] = 'user'
                os.environ['OBSRVBL_SNMP_VERSION'] = '3'
                os.environ['OBSRVBL_SNMPV3_ENGINEID'] = '01020304'
                os.environ['OBSRVBL_SNMPV3_PASSPHRASE'] = 'opensesame'

                pub = NotificationPublisher()

                messages = []
                messages.append('foobar')
                pub.publish(messages, 'error')

            msg = server.pop()
            self.assertRegexpMatches(msg, 'foobar')

        self.assertEquals(mock_snmp.call_args_list, [
            call(objectID='1.3.6.1.4.1.3375.2.100', port=162, host='localhost',
                 user='user', version='3', passcode='opensesame',
                 engineID='01020304'),
        ])

    @patch('ona_service.notification_publisher.utcnow', autospec=True)
    @patch('ona_service.api.Api.get_data', autospec=True)
    @patch('ona_service.notification_publisher.create_logger', autospec=True)
    def test_execute_default(self, mock_create_logger, mock_get, mock_now):
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger

        messages = [
            {'id': 1, 'time': '2015-05-01T01:02:03+00:00'},
            {'id': 2, 'time': '2015-05-01T01:02:04+00:00'},
            {'id': 3, 'time': '2015-05-01T01:02:05+00:00'},
        ]
        mock_get.return_value.json.return_value = {'objects': messages}

        now = datetime.utcnow().replace(tzinfo=utc)
        mock_now.return_value = now
        default_params = {'time__gt': now.isoformat()}

        pub = NotificationPublisher()
        pub.execute()

        self.assertEquals(mock_get.call_args_list, [
            call(pub.api, 'alerts', default_params),
            call(pub.api, 'observations', default_params),
        ])

        self.assertEquals(mock_logger.info.call_args_list, [
            call(m) for m in messages
        ])
        self.assertEquals(mock_logger.error.call_args_list, [
            call(m) for m in messages
        ])

        with open(STATE_FILE, 'r') as f:
            state = json.load(f)

        self.assertEquals(
            state,
            {
                'alerts': {'time__gt': '2015-05-01T01:02:05+00:00'},
                'observations': {'time__gt': '2015-05-01T01:02:05+00:00'}
            }
        )

    @patch('ona_service.notification_publisher.utcnow', autospec=True)
    @patch('ona_service.api.Api.get_data', autospec=True)
    @patch('ona_service.notification_publisher.create_logger', autospec=True)
    def test_execute_noresults(self, mock_create_logger, mock_get, mock_now):
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger

        mock_get.return_value.json.side_effect = ValueError

        now = datetime.utcnow().replace(tzinfo=utc)
        mock_now.return_value = now
        default_params = {'time__gt': now.isoformat()}

        pub = NotificationPublisher()
        pub.execute()

        self.assertEquals(mock_get.call_args_list, [
            call(pub.api, 'alerts', default_params),
            call(pub.api, 'observations', default_params),
        ])

        self.assertEquals(mock_logger.info.call_args_list, [])
        self.assertEquals(mock_logger.error.call_args_list, [])

        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        self.assertEquals(state, {
            'alerts': default_params,
            'observations': default_params,
        })

    @patch('ona_service.api.Api.get_data', autospec=True)
    @patch('ona_service.notification_publisher.create_logger', autospec=True)
    def test_execute_resume(self, mock_create_logger, mock_get):
        last_alert_time = '2015-05-01T01:02:03+00:00'
        last_obs_time = '2015-05-01T01:02:02+00:00'

        state = {
            'alerts': {'time__gt': last_alert_time},
            'observations': {'time__gt': last_obs_time}
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)

        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger

        messages = [{'id': 5, 'time': '2015-05-01T01:02:05+00:00'}]
        mock_get.return_value.json.return_value = {'objects': messages}

        pub = NotificationPublisher()
        pub.execute()

        self.assertEquals(
            mock_get.call_args_list,
            [
                call(pub.api, 'alerts', {'time__gt': last_alert_time}),
                call(pub.api, 'observations', {'time__gt': last_obs_time}),
            ]
        )

        self.assertEquals(mock_logger.info.call_args_list, [
            call(m) for m in messages
        ])
        self.assertEquals(mock_logger.error.call_args_list, [
            call(m) for m in messages
        ])

        with open(STATE_FILE, 'r') as f:
            state = json.load(f)

        self.assertEquals(
            state,
            {
                'alerts': {'time__gt': '2015-05-01T01:02:05+00:00'},
                'observations': {'time__gt': '2015-05-01T01:02:05+00:00'}
            }
        )

    @patch('ona_service.api.Api.get_data', autospec=True)
    def test_service(self, mock_get):
        mock_get.return_value.json.return_value = {'objects': []}

        pub = NotificationPublisher()
        pub.poll_seconds = 0

        def killer(signum, frame):
            pub.stop()
        signal.signal(signal.SIGALRM, killer)
        signal.alarm(1)
        pub.run()
