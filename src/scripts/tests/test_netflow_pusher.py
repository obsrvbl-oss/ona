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
from os import listdir
from os.path import join
from unittest import TestCase

from mock import call as MockCall, MagicMock, patch

from ona_service.netflow_pusher import NetflowPusher

from tests.test_pusher import PusherTestBase


class NetflowPusherTestCase(PusherTestBase, TestCase):
    def setUp(self):
        self.inst = self._get_instance(NetflowPusher)
        self.inst._process_files = MagicMock()
        self.tar_read_mode = 'r'
        super(NetflowPusherTestCase, self).setUp()

    def _touch_files(self):
        # Files ready for processing
        self.ready = [
            'nfcapd.201403241350',
            'nfcapd.201403241359',
            'nfcapd.201403241400',
            'nfcapd.201403241409',
        ]

        # Files still in use
        self.waiting = [
            'nfcapd.201403241410',
            'nfcapd.201403241411',
            'nfcapd.201403241419',
        ]

        # Files created by tar cf
        self.output = [
            'nfcapd.201403241350.foo',
            'nfcapd.201403241400.foo',
        ]

        # Touch all the input files
        for file_name in (self.ready + self.waiting):
            file_path = join(self.input_dir, file_name)
            open(file_path, 'w').close()

        # Touch all the output file
        for file_name in self.output:
            file_path = join(self.output_dir, file_name)
            open(file_path, 'w').close()

    @patch('ona_service.netflow_pusher.call', autospec=True)
    def test_process_files(self, mock_call):
        inst = self._get_instance(NetflowPusher)

        input_paths = [join(self.input_dir, x) for x in self.ready[0:2]]
        inst._process_files(input_paths)

        default_filter = (
            '(net 10.0.0.0/8) or (net 172.16.0.0/12) or (net 192.168.0.0/16)'
        )
        expected_calls = []
        for file_path in input_paths:
            args = [
                'nfdump',
                '-r', '{}.tmp'.format(file_path),
                '-w', file_path,
                '-z',
                default_filter
            ]
            expected_calls.append(MockCall(args))

        self.assertEqual(mock_call.call_args_list, expected_calls)

        # Make sure the temporary files were deleted
        actual = listdir(self.input_dir)
        expected = self.ready + self.waiting
        self.assertItemsEqual(actual, expected)
