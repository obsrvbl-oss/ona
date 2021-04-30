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
import time

from datetime import datetime
from ipaddress import ip_address, IPv6Address
from os import environ, fsync, remove
from tempfile import NamedTemporaryFile
from unittest import TestCase
from unittest.mock import patch

from ona_service.utils import (
    CommandOutputFollower,
    exploded_ip,
    get_ip,
    utcoffset,
    validate_pna_networks,
    is_ip_address,
)


class CommandOutputFollowerTestCase(TestCase):
    def setUp(self):
        self.file_path = NamedTemporaryFile(delete=False).name
        self.command_args = ['tail', '-f', '-n', '0', self.file_path]

    def tearDown(self):
        remove(self.file_path)

    def _write_line(self, text):
        with open(self.file_path, 'ab') as outfile:
            outfile.write(text + b'\n')
            fsync(outfile.fileno())

    def test_usage(self):
        # Write two lines before we start
        self._write_line(b'Hartnell')
        self._write_line(b'Troughton')

        with CommandOutputFollower(self.command_args) as follower:
            # The process has started, yes?
            self.assertTrue(follower.check_process())

            # Try a read. We shouldn't see the lines that existed before we
            # started following.
            self.assertIsNone(follower.read_line(1), None)

            # Try to read a third line. We shouldn't get anything.
            self._write_line(b'Pertwee')
            self.assertEqual(follower.read_line(1), b'Pertwee\n')

            # Write some more lines. Can we read them?
            self._write_line(b'Baker')
            self._write_line(b'Davison')
            self.assertEqual(follower.read_line(1), b'Baker\n')
            self.assertEqual(follower.read_line(1), b'Davison\n')

        # The process has stopped, yes?
        self.assertFalse(follower.check_process())


class GetIpTestCase(TestCase):
    @patch('socket.socket', autospec=True)
    def test_returns_proper_ip(self, mock_socket):
        mock_socket.return_value.getsockname.return_value = (
            '192.0.2.1', 49152
        )
        self.assertEqual('192.0.2.1', get_ip())
        self.assertEqual(mock_socket.return_value.connect.call_count, 1)
        self.assertEqual(mock_socket.return_value.shutdown.call_count, 1)
        self.assertEqual(mock_socket.return_value.close.call_count, 1)


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


class ExplodedIPTests(TestCase):
    def test_basic(self):
        for item in ['192.0.2.0', '2001:db8::', '::ffff:192.168.1.1']:
            with self.subTest(item=item):
                actual = exploded_ip(item)
                expected = (
                    IPv6Address(int(ip_address(item)))
                    .exploded
                    .replace(':', '')
                )
                self.assertEqual(actual, expected)

    def test_error(self):
        for item in [
            '192.0.2.256',
            '2001:db8:::',
            'localhost',
            'example.org',
            '192.0.2.0:443',
        ]:
            with self.assertRaises(OSError):
                exploded_ip(item)
