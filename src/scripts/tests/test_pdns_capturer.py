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

from datetime import datetime
from os import getenv, listdir
from os.path import exists, join
from shutil import rmtree
from unittest import TestCase

from mock import call, MagicMock, patch

from ona_service.pdns_capturer import PdnsCapturer
PATCH_PATH = 'ona_service.pdns_capturer.{}'


class PdnsCapturerTestCase(TestCase):
    def setUp(self):
        self.inst = PdnsCapturer()

    def tearDown(self):
        rmtree(self.inst.pcap_dir)

    def test_init(self):
        # Make sure the directory was created
        self.assertTrue(exists(self.inst.pcap_dir))

    def test_check_capture(self):
        # No capture process -> False
        self.assertFalse(self.inst.check_capture())

        # Capture process exited early -> False
        self.inst.capture_process = MagicMock()
        self.inst.capture_process.poll.return_value = 1
        self.assertFalse(self.inst.check_capture())

        # Capture process still going -> True
        self.inst.capture_process.poll.return_value = None
        self.assertTrue(self.inst.check_capture())

    @patch('ona_service.tcpdump_capturer.Popen', autospec=True)
    def test_start_capture(self, mock_Popen):
        self.inst.start_capture()
        tcpdump_args = [
            'sudo',
            '/usr/sbin/tcpdump',
            '-w', join(self.inst.pcap_dir, 'pdns_%s.pcap'),
            '-i', self.inst.capture_iface,
            '-s', '0',
            '-c', '{}'.format(self.inst.packet_limit),
            '-G', '{}'.format(self.inst.capture_seconds),
            '-U',
            '-Z', 'obsrvbl_ona',
            'ip and udp src port 53'
        ]
        mock_Popen.assert_called_once_with(tcpdump_args)

    @patch('ona_service.tcpdump_capturer.platform', 'freebsd10')
    @patch('ona_service.tcpdump_capturer.Popen', autospec=True)
    def test_start_capture_freebsd(self, mock_Popen):
        inst = PdnsCapturer()
        inst.start_capture()
        tcpdump_args = [
            'sudo',
            '/usr/sbin/tcpdump',
            '-w', join(inst.pcap_dir, 'pdns_%s.pcap'),
            '-s', '0',
            '-c', '{}'.format(inst.packet_limit),
            '-G', '{}'.format(inst.capture_seconds),
            '-U',
            '-Z', 'obsrvbl_ona',
            'ip and udp src port 53'
        ]
        mock_Popen.assert_called_once_with(tcpdump_args)

    @patch('ona_service.pdns_capturer.getenv', autospec=True)
    @patch('ona_service.tcpdump_capturer.Popen', autospec=True)
    def test_start_capture_freebsd_specific(self, mock_Popen, mock_getenv):
        def getenv_side_effect(*args, **kwargs):
            if args[0] == 'OBSRVBL_PDNS_CAPTURE_IFACE':
                return 'em1'
            return getenv(*args, **kwargs)

        mock_getenv.side_effect = getenv_side_effect

        inst = PdnsCapturer()
        inst.start_capture()
        tcpdump_args = [
            'sudo',
            '/usr/sbin/tcpdump',
            '-w', join(inst.pcap_dir, 'pdns_%s.pcap'),
            '-i', 'em1',
            '-s', '0',
            '-c', '{}'.format(inst.packet_limit),
            '-G', '{}'.format(inst.capture_seconds),
            '-U',
            '-Z', 'obsrvbl_ona',
            'ip and udp src port 53'
        ]
        mock_Popen.assert_called_once_with(tcpdump_args)

    def test_compress_pcaps(self):
        # Touch some pcap files
        for n in (1, 2, 3):
            file_path = join(self.inst.pcap_dir, 'pdns_{}.pcap'.format(n))
            with io.open(file_path, 'wb'):
                pass

        # Before compression - nothing should be compressed
        actual = sorted(listdir(self.inst.pcap_dir))
        expected = ['pdns_1.pcap', 'pdns_2.pcap', 'pdns_3.pcap']
        self.assertEqual(actual, expected)

        # After compression - all but the last should be compressed
        self.inst.compress_pcaps()
        actual = sorted(listdir(self.inst.pcap_dir))
        expected = ['pdns_1.pcap.gz', 'pdns_2.pcap.gz', 'pdns_3.pcap']
        self.assertEqual(actual, expected)

    def test_push_files(self):
        # Touch some pcap.gz files
        for n in (1, 2):
            file_path = join(self.inst.pcap_dir, 'pdns_{}.pcap.gz'.format(n))
            with io.open(file_path, 'wb'):
                pass

        # Before pushing - should have all files available
        actual = sorted(listdir(self.inst.pcap_dir))
        expected = ['pdns_1.pcap.gz', 'pdns_2.pcap.gz']
        self.assertEqual(actual, expected)

        # After pushing - all files should be removed
        self.inst.api.send_file = MagicMock()
        now = datetime(2015, 3, 10, 16, 39, 56, 1020)
        self.inst.push_files(now)
        actual = sorted(listdir(self.inst.pcap_dir))
        expected = []
        self.assertEqual(actual, expected)

        # Send file should have been called on each file
        path_1 = join(self.inst.pcap_dir, 'pdns_1.pcap.gz')
        path_2 = join(self.inst.pcap_dir, 'pdns_2.pcap.gz')
        ts = datetime(2015, 3, 10, 16, 30, 0, 0)
        expected = [
            call('pdns', path_1, ts, suffix='0000'),
            call('pdns', path_2, ts, suffix='0001'),
        ]
        self.inst.api.send_file.assert_has_calls(expected, any_order=True)

    @patch(PATCH_PATH.format('PdnsCapturer.check_capture'), autospec=True)
    @patch(PATCH_PATH.format('PdnsCapturer.start_capture'), autospec=True)
    @patch(PATCH_PATH.format('PdnsCapturer.compress_pcaps'), autospec=True)
    @patch(PATCH_PATH.format('PdnsCapturer.push_files'), autospec=True)
    def test_execute(self, mock_push, mock_compress, mock_start, mock_check):
        mock_check.return_value = False
        self.inst.execute()
        self.assertEqual(mock_check.call_count, 1)
        self.assertEqual(mock_start.call_count, 1)
        self.assertEqual(mock_compress.call_count, 1)
        self.assertEqual(mock_push.call_count, 1)

        mock_check.return_value = True
        self.inst.execute()
        self.assertEqual(mock_check.call_count, 2)
        self.assertEqual(mock_start.call_count, 1)
        self.assertEqual(mock_compress.call_count, 2)
        self.assertEqual(mock_push.call_count, 2)
