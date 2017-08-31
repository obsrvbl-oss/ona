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
from os import listdir
from os.path import exists, join
from shutil import rmtree
from unittest import TestCase

from mock import call, MagicMock, patch

from ona_service.pdns_pusher import PdnsPusher
PATCH_PATH = 'ona_service.pdns_pusher.{}'


class PdnsPusherTestCase(TestCase):
    def setUp(self):
        self.inst = PdnsPusher()

    def tearDown(self):
        rmtree(self.inst.pcap_dir)

    def test_init(self):
        # Make sure the directory was created
        self.assertTrue(exists(self.inst.pcap_dir))

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

    @patch(PATCH_PATH.format('PdnsPusher.compress_pcaps'), autospec=True)
    @patch(PATCH_PATH.format('PdnsPusher.push_files'), autospec=True)
    def test_execute(self, mock_push, mock_compress):
        self.inst.execute()
        self.assertEqual(mock_compress.call_count, 1)
        self.assertEqual(mock_push.call_count, 1)
