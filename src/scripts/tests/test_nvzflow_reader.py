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
import logging

from binascii import unhexlify
from json import loads
from os.path import join
from shutil import rmtree
from unittest import TestCase
from tempfile import mkdtemp

from mock import patch

import ona_service.nvzflow_reader

from ona_service.nvzflow_reader import (
    ENV_NVZFLOW_LOG_DIR,
    logger as module_logger,
    NVZFlowHandler,
    NVZFlowReader,
    NVZFLOW_TEMPLATE,
)

TEMPLATE_MESSAGE = unhexlify(
    b'000a01e858e463ce000000010000007f000201d801060007015effffb02c0014000000'
    b'09b02effff00000009b02fffff00000009b03fffff00000009b030ffff00000009b031'
    b'ffff00000009010b0019000400010008000400070002000c0004000b00020096000400'
    b'970004b02c001400000009b02dffff00000009b049000200000009b032ffff00000009'
    b'b04a000200000009b034ffff00000009b035002000000009b033ffff00000009b04b00'
    b'0200000009b036ffff00000009b037002000000009b03a000800000009b03b00080000'
    b'0009b038ffff00000009b039ffff00000009b043000400000009b040ffff00000009b0'
    b'41ffff00000009010c001900040001001b001000070002001c0010000b000200960004'
    b'00970004b02c001400000009b02dffff00000009b049000200000009b032ffff000000'
    b'09b04a000200000009b034ffff00000009b035002000000009b033ffff00000009b04b'
    b'000200000009b036ffff00000009b037002000000009b03a000800000009b03b000800'
    b'000009b038ffff00000009b039ffff00000009b043000400000009b040ffff00000009'
    b'b041ffff00000009010a0007b02c001400000009b043000400000009b0440004000000'
    b'09b045000100000009b046ffff00000009b047ffff00000009b048ffff00000009'
)

DATA_MESSAGE_267 = unhexlify(
    # IPFIX header
    b'000a02d058e463d8000000160000007f'
    # FlowSet header
    b'010b02c0'
    # protocolIdentifier
    b'11'
    # sourceIPv4Address
    b'c0a8000a'
    # sourceTransportPort
    b'ab67'
    # destinationIPv4Address
    b'c0a8000b'
    # destinationTransportPort
    b'0035'
    # flowStartSeconds
    b'58e463d5'
    # flowEndSeconds
    b'58e463d5'
    # 12332 - nvzFlowUDID
    b'4ca7d9a79889dc4f18b4cd1b7e9f7e25d0c866a4'
    # 12333
    b'0d4d594e564d5c64756d6d793131'
    # 12361
    b'0002'
    # 12338
    b'1c4e5420415554484f524954595c4e4554574f524b2053455256494345'
    # 12362
    b'0001'
    # 12340
    b'0b737663686f73742e657865'
    # 12341
    b'740a46a0f5e0e8c933efd28c9901e54e42792619'
    # 12339
    b'a8a3a6d11e1f0025a7324bc2'
    # 12363
    b'134e5420415554484f524954595c53595354454d'
    # 12342
    b'0002'
    b'0c73657276696365732e657865'
    # 12433
    b'd7bc4ed605b32274b45328fd9914fb0e7b90d869a38f0e6f94fb1bf4e9e2b407'
    # 12346: nvzFlowL4ByteCountIn
    b'0000000000000064'
    # 12347: nvzFlowL4ByteCountOut
    b'0000000000000029'
    # 12344
    b'0864756d6d792e6475'
    # 12345
    b'07556e6b6e6f776e'
    # 12355
    b'00000006'
    # 12352
    b'ff008103b03cffff000000090c63727970747376632e646c6c0c64686370636f72652e'
    b'646c6c0b7465726d7372762e646c6c0c646e7372736c76722e646c6c0a776b73737663'
    b'2e646c6c0c716167656e7452542e646c6c0a6e6c617376632e646c6c0a57736d537663'
    b'2e646c6c0a7765637376632e646c6c0b746170697372762e646c6c'
    # 12353
    b'ff014903b03e002000000009340df730e88f8b6a4ef542f620eba2a720546afa'
    b'b4dffa00f066b7610a1026c54d9037b458c522874619143a4176bced42472c68933e6e'
    b'83d37b67242706f3c45f52c2e7902024cf1c9cc0069f411c3f19cca3db209f437fa0f3'
    b'932d4898eb5016060ddc32ef95eb6e37b91d50a96ab53cb0debb3dfdcb31975d163610'
    b'92aba5c3e6519a1a38f1b3597d4391e42abfe8f1f5e86256c4b3bd876cdad9bb68b0a6'
    b'd252248532142e9e2332da693bc51b795102ca938b568ff04981e98b19bfbc5c99b8cd'
    b'043df531d4b9725ed167f63ced220608b2fed3ee8250c217d15762dfd75b6618615ebf'
    b'ba594c945ad35f5c68da8c6053892b6d12d626bb6120910d80dca53940ba28854486ff'
    b'18f16b98a3314b36322b0b6efb54d08b921315beb0add5fcff02e466d2501630b45262'
    b'7fb218c01e5245a0921ee3d2117e7fd63ac7e98e'
)

DATA_MESSAGE_262 = unhexlify(
    # IPFIX Header
    b'000a00555ac652060007bc010000007f'
    # FlowSet Header
    b'01060045'
    # virtualStationName
    b'0e53544154494f4e2d313032303130'
    # 12332 - nvzFlowUDID
    b'4ca7d9a79889dc4f18b4cd1b7e9f7e25d0c866a4'
    # 12334
    b'084d6163204f532058'
    # 12335
    b'0731302e31322e36'
    # 12351
    b'06536965727261'
    # 12336
    b'012d'
    # 12337
    b'03783634'
)


class NVZFlowReaderTests(TestCase):
    def setUp(self):
        self.temp_dir = mkdtemp()
        env = {ENV_NVZFLOW_LOG_DIR: self.temp_dir}
        with patch.dict('ona_service.nvzflow_reader.environ', env):
            self.nvzflow_reader = NVZFlowReader()

    def tearDown(self):
        rmtree(self.temp_dir, ignore_errors=True)

    def _read_current_log(self):
        with io.open(join(self.temp_dir, 'nvzflow.log'), 'rt') as infile:
            return [loads(line) for line in infile]

    def test_handle_message(self):
        self.nvzflow_reader.handle_message(TEMPLATE_MESSAGE)
        self.nvzflow_reader.handle_message(DATA_MESSAGE_267)
        actual = self._read_current_log()
        expected = [
            {
                'sourceIPv4Address': '192.168.0.10',
                'destinationIPv4Address': '192.168.0.11',
                'sourceTransportPort': 43879,
                'destinationTransportPort': 53,
                'protocolIdentifier': 17,
                'flowStartSeconds': 0x58e463d5,
                'flowEndSeconds': 0x58e463d5,
                'nvzFlowL4ByteCountIn': 0x0000000000000064,
                'nvzFlowL4ByteCountOut': 0x0000000000000029,
                'nvzFlowUDID': '4ca7d9a79889dc4f18b4cd1b7e9f7e25d0c866a4',
            }
        ]
        self.assertEqual(actual, expected)

    def test_handle_message_no_template(self):
        self.nvzflow_reader.handle_message(DATA_MESSAGE_267)
        actual = self._read_current_log()
        expected = []
        self.assertEqual(actual, expected)

    def test_handle_message_preloaded_template(self):
        self.nvzflow_reader.known_templates.update(NVZFLOW_TEMPLATE)
        self.nvzflow_reader.handle_message(DATA_MESSAGE_267)
        actual = self._read_current_log()
        expected = [
            {
                'sourceIPv4Address': '192.168.0.10',
                'destinationIPv4Address': '192.168.0.11',
                'sourceTransportPort': 43879,
                'destinationTransportPort': 53,
                'protocolIdentifier': 17,
                'flowStartSeconds': 0x58e463d5,
                'flowEndSeconds': 0x58e463d5,
                'nvzFlowL4ByteCountIn': 0x0000000000000064,
                'nvzFlowL4ByteCountOut': 0x0000000000000029,
                'nvzFlowUDID': '4ca7d9a79889dc4f18b4cd1b7e9f7e25d0c866a4',
            }
        ]
        self.assertEqual(actual, expected)

    def test_handle_endpoint_id_message(self):
        self.nvzflow_reader.known_templates.update(NVZFLOW_TEMPLATE)
        self.nvzflow_reader.handle_message(DATA_MESSAGE_262)
        actual = self._read_current_log()
        expected = [
            {
                'nvzFlowUDID': '4ca7d9a79889dc4f18b4cd1b7e9f7e25d0c866a4',
                'virtualStationName': 'STATION-102010',
            }
        ]
        self.assertEqual(actual, expected)

    def test_handle_partial_message(self):
        # Brazenly truncate messages and see if something bad happens
        module_logger.setLevel(logging.CRITICAL)  # Shh, it's OK...
        for i in range(len(TEMPLATE_MESSAGE) + 1):
            self.nvzflow_reader.handle_message(TEMPLATE_MESSAGE[:i])

        for i in range(len(DATA_MESSAGE_267) + 1):
            self.nvzflow_reader.handle_message(DATA_MESSAGE_267[:i])

    def test_NVZFlowHandler(self):
        self.assertIsNone(ona_service.nvzflow_reader.nvzflow_reader)
        ona_service.nvzflow_reader.nvzflow_reader = self.nvzflow_reader
        self.assertIsNotNone(ona_service.nvzflow_reader.nvzflow_reader)
        NVZFlowHandler((TEMPLATE_MESSAGE, None), None, None)
        NVZFlowHandler((DATA_MESSAGE_267, None), None, None)
        actual = self._read_current_log()
        expected = [
            {
                'sourceIPv4Address': '192.168.0.10',
                'destinationIPv4Address': '192.168.0.11',
                'sourceTransportPort': 43879,
                'destinationTransportPort': 53,
                'protocolIdentifier': 17,
                'flowStartSeconds': 0x58e463d5,
                'flowEndSeconds': 0x58e463d5,
                'nvzFlowL4ByteCountIn': 0x0000000000000064,
                'nvzFlowL4ByteCountOut': 0x0000000000000029,
                'nvzFlowUDID': '4ca7d9a79889dc4f18b4cd1b7e9f7e25d0c866a4',
            }
        ]
        self.assertEqual(actual, expected)
