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
from gzip import open as gz_open
from os import listdir
from os.path import join
from unittest import TestCase
from unittest.mock import call as MockCall, MagicMock, patch

from ona_service.ipfix_pusher import (
    CSV_HEADER,
    ENV_IPFIX_INDEX_RANGES,
    get_index_filter,
    IPFIXPusher,
    RWFILTER_PATH,
    RWUNIQ_PATH,
)

from tests.test_pusher import PusherTestBase


class IPFIXPusherTestCase(PusherTestBase, TestCase):
    def setUp(self):
        self.data_type = 'ipfix'
        self.inst = self._get_instance(IPFIXPusher)
        self.inst._process_files = MagicMock()
        self.tar_read_mode = 'r'
        super().setUp()

    def _touch_files(self):
        # Files ready for processing
        self.ready = [
            '20140324135011_S1.abcdef',
            '20140324135922_S1.ghijkl',
            '20140324140033_S1.mnopqr',
            '20140324140944_S1.stuvwx',
        ]

        # Files still in use
        self.waiting = [
            '20140324141055_S1.abcdef',
            '20140324141166_S1.ghijkl',
            '20140324141977_S1.mnopqr',
        ]

        # Files created by tar
        self.output = [
            '201403241350.foo',
            '201403241400.foo',
        ]

        # Touch all the input files
        for file_name in (self.ready + self.waiting):
            file_path = join(self.input_dir, file_name)
            open(file_path, 'w').close()

        # Touch all the output file
        for file_name in self.output:
            file_path = join(self.output_dir, file_name)
            open(file_path, 'w').close()

    @patch('ona_service.ipfix_pusher.call', autospec=True)
    def test_process_files(self, mock_call):
        self._touch_files()
        inst = self._get_instance(IPFIXPusher)

        input_paths = [join(self.input_dir, x) for x in self.ready[0:2]]
        inst._process_files(input_paths)

        expected_calls = []
        for file_path in input_paths:
            temp_path = '{}.tmp'.format(file_path)
            rwfilter_args = [
                RWFILTER_PATH,
                '--pass-destination', file_path,
                '--any-cidr', '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16',
                temp_path,
            ]
            expected_calls.append(MockCall(rwfilter_args))

            rwuniq_args = [
                RWUNIQ_PATH,
                '--no-titles',
                '--no-columns',
                '--no-final-delimiter',
                '--sort-output',
                '--column-sep', ',',
                '--timestamp-format', 'epoch',
                '--fields', 'sIp,dIp,sPort,dPort,protocol',
                '--values', 'Bytes,Packets,sTime-Earliest,eTime-Latest',
                '--output-path', temp_path,
                file_path,
            ]
            expected_calls.append(MockCall(rwuniq_args))

        self.assertEqual(mock_call.call_args_list, expected_calls)

        # Make sure the temporary files were deleted
        actual = listdir(self.input_dir)
        expected = self.ready + self.waiting
        self.assertCountEqual(actual, expected)

    @patch('ona_service.ipfix_pusher.call', autospec=True)
    def test_process_files_index_filter(self, mock_call):
        self._touch_files()
        env_override = {ENV_IPFIX_INDEX_RANGES: '34048-34050,34052-34054'}
        with patch.dict('ona_service.ipfix_pusher.environ', env_override):
            inst = self._get_instance(IPFIXPusher)

        input_paths = [join(self.input_dir, x) for x in self.ready[0:2]]
        inst._process_files(input_paths)

        expected_calls = []
        for file_path in input_paths:
            temp_path = '{}.tmp'.format(file_path)
            rwfilter_args = [
                RWFILTER_PATH,
                '--pass-destination', file_path,
                '--any-cidr', '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16',
                '--any-index', '34048,34049,34050,34052,34053,34054',
                temp_path,
            ]
            expected_calls.append(MockCall(rwfilter_args))

            rwuniq_args = [
                RWUNIQ_PATH,
                '--no-titles',
                '--no-columns',
                '--no-final-delimiter',
                '--sort-output',
                '--column-sep', ',',
                '--timestamp-format', 'epoch',
                '--fields', 'sIp,dIp,sPort,dPort,protocol',
                '--values', 'Bytes,Packets,sTime-Earliest,eTime-Latest',
                '--output-path', temp_path,
                file_path,
            ]
            expected_calls.append(MockCall(rwuniq_args))

        self.assertEqual(mock_call.call_args_list, expected_calls)

        # Make sure the temporary files were deleted
        actual = listdir(self.input_dir)
        expected = self.ready + self.waiting
        self.assertCountEqual(actual, expected)

    @patch('ona_service.ipfix_pusher.call', autospec=True)
    def test_csv_header(self, mock_call):
        self._touch_files()
        flow_line = (
            '198.22.253.72,192.168.207.199,80,61391,6,'
            '58,1,1459535021,1459535021\n'
        )

        def side_effect(*args, **kwargs):
            if 'rwuniq' not in args[0][0]:
                return 0
            with open(args[0][14], 'wt') as f:
                f.write(flow_line)
            return 0

        mock_call.side_effect = side_effect

        inst = self._get_instance(IPFIXPusher)

        input_paths = [join(self.input_dir, x) for x in self.ready[0:1]]
        inst._process_files(input_paths)

        with gz_open(input_paths[0], 'rt') as infile:
            lines = infile.readlines()
            self.assertEqual(lines[0], CSV_HEADER + '\n')
            self.assertEqual(lines[1], flow_line)

    @patch('ona_service.ipfix_pusher.call', autospec=True)
    def test_fix_sonicwall(self, mock_call):
        self._touch_files()
        # For SonicWALL the timestamps get replaced
        flow_line = (
            '198.22.253.72,192.168.207.199,80,61391,6,'
            '58,1,1459535021,1459535021\n'
        )
        altered_line = (
            '198.22.253.72,192.168.207.199,80,61391,6,'
            '58,1,1395669540,1395669540\n'
        )

        def side_effect(*args, **kwargs):
            if 'rwuniq' not in args[0][0]:
                return 0
            with open(args[0][14], 'wt') as f:
                f.write(flow_line)
            return 0

        mock_call.side_effect = side_effect

        env_override = {'OBSRVBL_IPFIX_PROBE_1_SOURCE': 'sonicwall'}
        with patch.dict('ona_service.ipfix_pusher.environ', env_override):
            inst = self._get_instance(IPFIXPusher)
            input_paths = [join(self.input_dir, x) for x in self.ready[1:2]]
            inst._process_files(input_paths)

        with gz_open(input_paths[0], 'rt') as infile:
            lines = infile.readlines()
            self.assertEqual(lines[0], CSV_HEADER + '\n')
            self.assertEqual(lines[1], altered_line)

    @patch('ona_service.ipfix_pusher.call', autospec=True)
    def test_fix_meraki(self, mock_call):
        self._touch_files()
        # Intermediate report - will get subsumed by the next line
        flow_line_1 = (
            '198.22.253.72,192.168.207.199,80,61391,6,'
            '58,1,1459535021,1459535021\n'
        )
        # Final report before reset - this will show up in the output
        flow_line_2 = (
            '198.22.253.72,192.168.207.199,80,61391,6,'
            '158,1,1459535021,1459535021\n'
        )
        # After the reset - this won't show up
        flow_line_3 = (
            '198.22.253.72,192.168.207.199,80,61391,6,'
            '157,1,1459535021,1459535021\n'
        )
        # This one shows up because it's the last report
        flow_line_4 = (
            '198.22.253.72,192.168.207.199,80,61391,6,'
            '159,1,1459535021,1459535021\n'
        )

        altered_line_1 = (
            '192.168.207.199,198.22.253.72,61391,80,6,'
            '158,1,1395669540,1395669540\n'
        )
        altered_line_2 = (
            '192.168.207.199,198.22.253.72,61391,80,6,'
            '159,1,1395669540,1395669540\n'
        )

        def side_effect(*args, **kwargs):
            if 'rwcut' not in args[0][0]:
                return 0
            with open(args[0][11], 'wt') as f:
                f.write(flow_line_1)
                f.write(flow_line_2)
                f.write(flow_line_3)
                f.write(flow_line_4)
            return 0

        mock_call.side_effect = side_effect

        env_override = {'OBSRVBL_IPFIX_PROBE_1_SOURCE': 'meraki'}
        with patch.dict('ona_service.ipfix_pusher.environ', env_override):
            inst = self._get_instance(IPFIXPusher)
            input_paths = [join(self.input_dir, x) for x in self.ready[1:2]]
            inst._process_files(input_paths)

        with gz_open(input_paths[0], 'rt') as infile:
            lines = infile.readlines()
            self.assertEqual(len(lines), 1 + 2)  # Header + Rows
            self.assertEqual(lines[0], CSV_HEADER + '\n')
            self.assertEqual(lines[1], altered_line_1)
            self.assertEqual(lines[2], altered_line_2)

    @patch('ona_service.ipfix_pusher.call', autospec=True)
    def test_fix_asa(self, mock_call):
        self._touch_files()
        # For the ASA the protocols get fixed
        flow_line = (
            '198.22.253.72,192.168.207.199,80,61391,6,'
            '58,1,1459535021,1459535021\n'
        )
        fixable_line = (
            '192.168.207.199,198.22.253.72,61391,80,0,'
            '59,2,1459535022,1459535022\n'
        )
        fixed_line = (
            '192.168.207.199,198.22.253.72,61391,80,6,'
            '59,2,1459535022,1459535022\n'
        )
        unfixable_line = (
            '192.168.207.200,198.22.253.72,61391,80,0,'
            '59,2,1459535022,1459535022\n'
        )

        def side_effect(*args, **kwargs):
            if 'rwuniq' not in args[0][0]:
                return 0
            with open(args[0][14], 'wt') as f:
                f.write(flow_line)
                f.write(fixable_line)
                f.write(unfixable_line)
            return 0

        mock_call.side_effect = side_effect

        env_override = {'OBSRVBL_IPFIX_PROBE_1_SOURCE': 'asa'}
        with patch.dict('ona_service.ipfix_pusher.environ', env_override):
            inst = self._get_instance(IPFIXPusher)
            input_paths = [join(self.input_dir, x) for x in self.ready[0:1]]
            inst._process_files(input_paths)

        with gz_open(input_paths[0], 'rt') as infile:
            lines = infile.readlines()
            self.assertEqual(lines[0], CSV_HEADER + '\n')
            self.assertEqual(lines[1], flow_line)
            self.assertEqual(lines[2], fixed_line)
            self.assertEqual(lines[3], unfixable_line)

    def test_get_index_filter(self):
        for range_str, expected in [
            ('0-5', '0,1,2,3,4,5'),
            ('0-5,7-10', '0,1,2,3,4,5,7,8,9,10'),
            ('0-5,-7-10,12-13', '0,1,2,3,4,5,12,13'),  # Skip invalid
            ('0-5,7-65536, 12-13', '0,1,2,3,4,5,12,13'),  # Skip invalid
        ]:
            actual = get_index_filter(range_str)
            self.assertEqual(actual, expected)
