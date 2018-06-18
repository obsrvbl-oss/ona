#  Copyright 2018 Observable Networks
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
import json

from datetime import datetime
from gzip import open as gz_open
from os.path import join
from unittest import TestCase

from mock import call as MagicMock

from ona_service.nvzflow_pusher import NVZFlowPusher

from tests.test_pusher import PusherTestBase

LOG_DATA = [
    {
        'destinationIPv6Address': '2001:db8::100a',
        'destinationTransportPort': 53,
        'flowEndSeconds': 1522955857,
        'flowStartSeconds': 1522955857,
        'nvzFlowL4ByteCountIn': 0,
        'nvzFlowL4ByteCountOut': 0,
        'protocolIdentifier': 17,
        'sourceIPv6Address': '2001:db8::8e18',
        'sourceTransportPort': 58572,
        'nvzFlowUDID': '91ff4ae06c7843bc93c9c1572482f7cda3b87853',
    },
    {
        'nvzFlowUDID': '283b5cf9da964f69b941bc3b817ff2ac0076d73d',
        'virtualStationName': '-',
    },
    {
        'destinationIPv4Address': '198.51.100.50',
        'destinationTransportPort': 443,
        'flowEndSeconds': 1522955857,
        'flowStartSeconds': 1522955826,
        'nvzFlowL4ByteCountIn': 5113,
        'nvzFlowL4ByteCountOut': 639,
        'protocolIdentifier': 6,
        'sourceIPv4Address': '192.0.2.29',
        'sourceTransportPort': 56209,
        'nvzFlowUDID': '283b5cf9da964f69b941bc3b817ff2ac0076d73d',
    },
    {
        'nvzFlowUDID': '283b5cf9da964f69b941bc3b817ff2ac0076d73d',
        'virtualStationName': 'STATION-102010',
    },
    {
        'destinationIPv4Address': '198.51.100.50',
        'destinationTransportPort': 443,
        'flowEndSeconds': 1522955857,
        'flowStartSeconds': 1522955857,
        'nvzFlowL4ByteCountIn': 0,
        'nvzFlowL4ByteCountOut': 0,
        'protocolIdentifier': 6,
        'sourceIPv4Address': '0.0.0.0',
        'sourceTransportPort': 0,
        'nvzFlowUDID': '1bc6b38375a347539a2ddf048472d66fc806f3d5',
    },
    {
        'nvzFlowUDID': '1bc6b38375a347539a2ddf048472d66fc806f3d5',
        'virtualStationName': 'STATION-102011',
    },
]


class NVZFlowPusherTestCase(PusherTestBase, TestCase):
    def setUp(self):
        self.data_type = 'csv'
        self.inst = self._get_instance(NVZFlowPusher)
        self.inst._process_files = MagicMock()
        self.tar_read_mode = 'r'
        super(NVZFlowPusherTestCase, self).setUp()

    def _touch_files(self):
        # Files ready for processing
        self.ready = [
            'nvzflow.log.2014-03-24_13-50',
            'nvzflow.log.2014-03-24_13-59',
            'nvzflow.log.2014-03-24_14-00',
            'nvzflow.log.2014-03-24_14-09',
        ]

        # Files still in use
        self.waiting = [
            'nvzflow.log.2014-03-24_14-10',
            'nvzflow.log.2014-03-24_14-11',
            'nvzflow.log.2014-03-24_14-19',
        ]

        # Files created by tar
        self.output = [
            'nvzflow.log.2014-03-24_13-50.foo',
            'nvzflow.log.2014-03-24_14-00.foo',
        ]

        # Touch all the input files
        for file_name in (self.ready + self.waiting):
            file_path = join(self.input_dir, file_name)
            io.open(file_path, 'w').close()

        # Touch all the output file
        for file_name in self.output:
            file_path = join(self.output_dir, file_name)
            io.open(file_path, 'w').close()

    def test_process_files(self):
        # Write some test data
        file_path = join(self.input_dir, 'nvzflow.log')
        with io.open(file_path, 'wt') as f:
            for line in LOG_DATA:
                print(json.dumps(line).decode('utf-8'), file=f)

        # Process it
        inst = self._get_instance(NVZFlowPusher)
        inst._process_files([file_path])

        # It should have turned from JSON-object-per-line to CSV with header
        with gz_open(file_path, 'rt') as f:
            actual = f.read()
        expected = (
            'srcaddr,dstaddr,srcport,dstport,protocol,'
            'bytes_in,bytes_out,start,end\r\n'
            '2001:db8::8e18,2001:db8::100a,58572,53,17,'
            '0,0,1522955857,1522955857\r\n'
            '192.0.2.29,198.51.100.50,56209,443,6,'
            '5113,639,1522955826,1522955857\r\n'
            '0.0.0.0,198.51.100.50,0,443,6,'
            '0,0,1522955857,1522955857\r\n'
        )
        self.assertEqual(actual, expected)

    def test_execute_hostnames(self):
        # Write some test data
        file_path = join(self.input_dir, 'nvzflow.log')
        with io.open(file_path, 'wt') as f:
            for line in LOG_DATA:
                print(json.dumps(line).decode('utf-8'), file=f)

        # Process it
        inst = self._get_instance(NVZFlowPusher)
        inst._process_files([file_path])

        actual_data = []

        def side_effect(data_type, path, now, suffix=None):
            with io.open(path, mode='rb') as f:
                actual_data.append(f.read())

            return 'https://127.0.0.1/hostnames/target'

        inst.api.send_file.side_effect = side_effect
        inst.execute(now=datetime.now())

        # The valid hostname data should be sent out
        self.assertEqual(
            json.loads(actual_data[0].decode('utf-8')),
            {'192.0.2.29': 'STATION-102010'}
        )
        inst.api.send_signal.assert_any_call(
           'hostnames', {'path': 'https://127.0.0.1/hostnames/target'}
        )
