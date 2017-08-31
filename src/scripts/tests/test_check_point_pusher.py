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
from __future__ import print_function, division, unicode_literals

import io

from datetime import datetime
from os import environ
from os.path import join
from shutil import rmtree
from tempfile import mkdtemp
from unittest import TestCase

from mock import patch, MagicMock

from ona_service.check_point_pusher import (
    CheckPointPusher,
    ENV_CHECK_POINT_PATH,
)
from ona_service.utils import gunzip_bytes

from tests.test_pusher import PusherTestBase

LOG_DATA = (
    # This line came in too late
    'Jun  2 15:11:24 192.0.2.1  2016-06-02T14:59:07--5:00 192.0.2.1 '
    'CP-GW - Log [Fields@1.3.6.1.4.1.2620 Action="allow" '
    'src="192.0.2.0" dst="198.51.100.0" proto="17" sent_bytes="200" '
    'received_bytes="100" service="8080" s_port="32768"]\n'
    # This is ready to send
    'Jun  2 15:12:24 192.0.2.1  2016-06-02T15:09:07--5:00 192.0.2.1 '
    'CP-GW - Log [Fields@1.3.6.1.4.1.2620 Action="allow" '
    'src="192.0.2.2" dst="198.51.100.1" proto="6" sent_bytes="100" '
    'received_bytes="200" service="80" s_port="47006"]\n'
    # This line isn't ready yet
    'Jun  2 15:13:24 192.0.2.1  2016-06-02T15:10:07--5:00 192.0.2.1 '
    'CP-GW - Log [Fields@1.3.6.1.4.1.2620 Action="allow" '
    'src="192.0.2.3" dst="198.51.100.2" proto="17" sent_bytes="200" '
    'received_bytes="300" service="443" s_port="49152"]\n'
    # Not a line we know how to read
    'Jun  2 15:14:24 192.0.2.1  Some other service!\n'
    # Missing some fields
    'Jun  2 15:15:24 192.0.2.1  2016-06-02T15:10:07--5:00 192.0.2.1 '
    'CP-GW - Log [Fields@1.3.6.1.4.1.2620 Action="allow" '
    'src="192.0.2.3" s_port="49152"]\n'
    # Weird date
    'Jun  2 15:15:24 192.0.2.1  2016-06-02Z15:10:07-05:00 192.0.2.1 '
    'CP-GW - Log [Fields@1.3.6.1.4.1.2620 Action="\x9dallow" '
    'src="192.0.2.3" s_port="49152"]\n'
)


def _append_file(file_path, data):
    with io.open(file_path, 'ab') as outfile:
        print(data, file=outfile, end='')


class CheckPointPusherTestCase(PusherTestBase, TestCase):
    def setUp(self):
        self.log_dir = mkdtemp()
        self.log_path = join(self.log_dir, 'check-point-fw.log')
        environ[ENV_CHECK_POINT_PATH] = self.log_path
        _append_file(self.log_path, '')

        self.data_type = 'csv'
        self.inst = self._get_instance(CheckPointPusher)
        self.inst._process_files = MagicMock()
        self.tar_read_mode = 'r'
        super(CheckPointPusherTestCase, self).setUp()

    def tearDown(self):
        rmtree(self.log_dir, ignore_errors=True)
        super(CheckPointPusherTestCase, self).tearDown()

    def _touch_files(self):
        # Files ready for processing
        self.ready = [
            '20140324135011_20140324141031.csv.gz',
            '20140324135912_20140324141032.csv.gz',
            '20140324140013_20140324141033.csv.gz',
            '20140324140914_20140324141034.csv.gz',
        ]

        # Files still in use
        self.waiting = [
            '20140324141015_20140324141035.csv.gz',
            '20140324141116_20140324141036.csv.gz',
            '20140324141917_20140324141037.csv.gz',
        ]

        # Files created by tar cf
        self.output = [
            '20140324135000.foo',
            '20140324140000.foo',
        ]

        # Touch all the input files
        for file_name in (self.ready + self.waiting):
            file_path = join(self.input_dir, file_name)
            open(file_path, 'w').close()

        # Touch all the output file
        for file_name in self.output:
            file_path = join(self.output_dir, file_name)
            open(file_path, 'w').close()

    def test_generate(self):
        inst = self._get_instance(CheckPointPusher)
        _append_file(self.log_path, LOG_DATA.encode('latin_1'))

        HEADER = (
            'srcaddr,dstaddr,srcport,dstport,protocol,'
            'bytes_in,bytes_out,start,end'
        )
        LINES = [
            (
                '192.0.2.2,198.51.100.1,47006,80,6,'
                '200,100,1464898147,1464898147'
            ),
            (
                '192.0.2.3,198.51.100.2,49152,443,17,'
                '300,200,1464898207,1464898207'
            ),
        ]

        for dt, expected_lines, file_name in (
            (
                datetime(2016, 6, 2, 20, 19, 0),
                [HEADER, LINES[0]],
                '20160602200000_20160602201900.csv.gz',
            ),
            (
                datetime(2016, 6, 2, 20, 21, 0),
                [HEADER, LINES[1]],
                '20160602201000_20160602202100.csv.gz',
            ),
        ):
            patch_path = 'ona_service.check_point_pusher.create_dirs'
            with patch(patch_path, autospec=True) as mock_create_dirs:
                inst.execute(dt)
                mock_create_dirs.assert_called_once_with(inst.input_dir)

            with io.open(join(inst.input_dir, file_name), 'rb') as infile:
                data = gunzip_bytes(infile.read())

            self.assertEqual(data.decode('utf-8').splitlines(), expected_lines)
