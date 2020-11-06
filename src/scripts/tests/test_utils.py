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
from __future__ import print_function

import time

from datetime import datetime
from json import dumps
from os import environ, fsync, remove
from os.path import exists, join
from shutil import rmtree
from tempfile import gettempdir, NamedTemporaryFile
from unittest import TestCase

from mock import call as MockCall, MagicMock, mock_open, patch

from ona_service.utils import (
    CommandOutputFollower,
    create_dirs,
    get_ip,
    utcnow,
    utcoffset,
    validate_pna_networks,
    send_observations,
    gzip_bytes,
    gunzip_bytes,
    is_ip_address,
)


class CommandOutputFollowerTestCase(TestCase):
    def setUp(self):
        self.file_path = NamedTemporaryFile(delete=False).name
        self.command_args = ['tail', '-f', '-n', '0', self.file_path]

    def tearDown(self):
        remove(self.file_path)

    def _write_line(self, text):
        with open(self.file_path, 'a') as outfile:
            print(text, file=outfile)
            fsync(outfile.fileno())

    def test_usage(self):
        # Write two lines before we start
        self._write_line('Hartnell')
        self._write_line('Troughton')

        with CommandOutputFollower(self.command_args) as follower:
            # The process has started, yes?
            self.assertTrue(follower.check_process())

            # Try a read. We shouldn't see the lines that existed before we
            # started following.
            self.assertIsNone(follower.read_line(1), None)

            # Try to read a third line. We shouldn't get anything.
            self._write_line('Pertwee')
            self.assertEqual(follower.read_line(1), 'Pertwee\n')

            # Write some more lines. Can we read them?
            self._write_line('Baker')
            self._write_line('Davison')
            self.assertEqual(follower.read_line(1), 'Baker\n')
            self.assertEqual(follower.read_line(1), 'Davison\n')

        # The process has stopped, yes?
        self.assertFalse(follower.check_process())


class CreateDirsTestCase(TestCase):
    def setUp(self):
        self.test_dir = join(gettempdir(), 'one', 'two', 'three')

    def tearDown(self):
        rmtree(join(gettempdir(), 'one'), ignore_errors=True)

    def test_new(self):
        self.assertFalse(exists(self.test_dir))
        create_dirs(self.test_dir)
        self.assertTrue(exists(self.test_dir))

    def test_existing(self):
        create_dirs(self.test_dir)
        self.assertTrue(exists(self.test_dir))
        create_dirs(self.test_dir)


class GetIpTestCase(TestCase):
    @patch('socket._socketobject.getsockname')
    def test_returns_proper_ip(self, mock_sockname):
        IP = '12.34.56.78'
        mock_sockname.return_value = (IP, 8765)
        self.assertEqual(IP, get_ip())


class UTCOffset(TestCase):
    def setUp(self):
        self.tz = environ.get('TZ')
        self.winter = datetime(2015, 1, 1, 6)
        self.summer = datetime(2015, 6, 1, 6)

    def tearDown(self):
        if self.tz:
            environ['TZ'] = self.tz
        else:
            del environ['TZ']
        time.tzset()

    def test_inutc(self):
        environ['TZ'] = 'Etc/UTC'
        time.tzset()
        self.assertEqual(utcoffset(self.summer), 0)
        self.assertEqual(utcoffset(self.winter), 0)

    def test_inuscentral(self):
        environ['TZ'] = 'US/Central'
        time.tzset()
        self.assertEqual(utcoffset(self.summer), -5 * 60 * 60)
        self.assertEqual(utcoffset(self.winter), -6 * 60 * 60)

    def test_inkathmandu(self):
        environ['TZ'] = 'Asia/Kathmandu'
        time.tzset()
        offset = int(5.75 * 60 * 60)
        self.assertEqual(utcoffset(self.summer), offset)
        self.assertEqual(utcoffset(self.winter), offset)


class ValidatePnaNetworksTestCase(TestCase):
    def test_valid(self):
        site_value = '10.0.0.0/8\n172.16.0.0/12\n192.168.0.0/16'
        actual = validate_pna_networks(site_value)
        expected = '10.0.0.0/8 172.16.0.0/12 192.168.0.0/16'
        self.assertEqual(actual, expected)

    def test_partial(self):
        site_value = '10.0.0.0/8\n172.16.0.0/12\n192.168.100.0/16'
        actual = validate_pna_networks(site_value)
        expected = '10.0.0.0/8 172.16.0.0/12 192.168.0.0/16'
        self.assertEqual(actual, expected)

        site_value = '10.0.0.0;8\n172.16.0.0/12\n192.168.100.0/16'
        actual = validate_pna_networks(site_value)
        expected = '172.16.0.0/12 192.168.0.0/16'
        self.assertEqual(actual, expected)

        site_value = '10.0.0.0/8\n2001:db8::ff00:42:8329/24'
        actual = validate_pna_networks(site_value)
        expected = '10.0.0.0/8'
        self.assertEqual(actual, expected)

        site_value = '10.0.0.0/8\n172.16.0.0.0/12'
        actual = validate_pna_networks(site_value)
        expected = '10.0.0.0/8'
        self.assertEqual(actual, expected)

        site_value = '10.0.0.0/8\n172.16.256.0/12'
        actual = validate_pna_networks(site_value)
        expected = '10.0.0.0/8'
        self.assertEqual(actual, expected)

    def test_none(self):
        site_value = '10.0.0.0;8'
        actual = validate_pna_networks(site_value)
        self.assertEqual(actual, '')

        site_value = 'adduser something evil'
        actual = validate_pna_networks(site_value)
        self.assertEqual(actual, '')

        site_value = None
        actual = validate_pna_networks(site_value)
        self.assertEqual(actual, '')


class SendObservationsTestCase(TestCase):
    def test_basic(self):
        api = MagicMock()
        data_path = 'file:///tmp/path.ext'
        api.send_file.return_value = data_path

        now = utcnow()

        m = mock_open()
        mock_path = 'ona_service.utils.NamedTemporaryFile'
        with patch(mock_path, m, create=True):
            send_observations(
                api=api,
                obs_type='some_type_v1',
                obs_data=[{'key': 'value'}, {'key': None}],
                now=now,
                suffix='some_suffix',
            )

        obs_1 = {'observation_type': 'some_type_v1', 'key': 'value'}
        obs_2 = {'observation_type': 'some_type_v1', 'key': None}
        m.return_value.write.assert_has_calls(
            [
                MockCall(dumps(obs_1, sort_keys=True).encode('utf-8')),
                MockCall(b'\n'),
                MockCall(dumps(obs_2, sort_keys=True).encode('utf-8')),
                MockCall(b'\n'),
            ]
        )

        self.assertEqual(api.send_file.call_count, 1)
        self.assertEqual(api.send_file.call_args[0][0], 'logs')
        self.assertEqual(api.send_file.call_args[0][2], now)
        self.assertEqual(api.send_file.call_args[1]['suffix'], 'some_suffix')

        data = {'path': data_path, 'log_type': 'observations'}
        api.send_signal.assert_called_once_with('logs', data)

    def test_empty(self):
        api = MagicMock()
        send_observations(api, 'some_type_v1', [], utcnow())
        self.assertEqual(api.send_file.call_count, 0)
        self.assertEqual(api.send_signal.call_count, 0)


class GzipTestCase(TestCase):
    def setUp(self):
        self.data = b'Test data'
        self.gz_data = (
            b'\x1f\x8b\x08\x00M\x986W\x02\xff\x0bI-.QHI,I\x04\x00\x11,\xf9Q\t'
            b'\x00\x00\x00'
        )

    def test_gunzip_bytes(self):
        self.assertEqual(gunzip_bytes(self.gz_data), self.data)

    def test_gzip_bytes(self):
        gz_data = gzip_bytes(self.data)
        self.assertEqual(gunzip_bytes(gz_data), self.data)


class IsIPAddressTests(TestCase):
    def test_basic(self):
        for item, expected in [
            ('192.0.2.0', True),
            ('2001:db8::', True),
            ('192.0.2.256', False),
            ('2001:db8:::', False),
            ('localhost', False),
            ('example.org', False),
            ('192.0.2.0:443', False),
        ]:
            actual = is_ip_address(item)
            self.assertEqual(actual, expected)
