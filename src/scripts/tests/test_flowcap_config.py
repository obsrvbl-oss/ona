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

from os import remove
from tempfile import NamedTemporaryFile
from unittest import TestCase

from mock import patch

from ona_service.flowcap_config import ENV_IPFIX_CONF, FlowcapConfig


class FlowcapConfigTestCase(TestCase):
    def setUp(self):
        self.ipfix_conf = NamedTemporaryFile(delete=False).name

        environ = {ENV_IPFIX_CONF: self.ipfix_conf}
        with patch.dict('ona_service.flowcap_config.environ', environ):
            self.flowcap_config = FlowcapConfig()

    def tearDown(self):
        remove(self.ipfix_conf)

    def test_basic(self):
        environ = {
            # Irrelevant variable
            'FOO': 'BAR',
            # Invalid index - ignored
            'OBSRVBL_IPFIX_PROBE_ZERO_TYPE': 'netflow-v5',
            # Valid probe
            'OBSRVBL_IPFIX_PROBE_0_TYPE': 'netflow-v5',
            'OBSRVBL_IPFIX_PROBE_0_PORT': '2055',
            # Invalid type - ignored
            'OBSRVBL_IPFIX_PROBE_1_TYPE': 'bogus',
            # Invalid port - ignored
            'OBSRVBL_IPFIX_PROBE_2_TYPE': 'netflow-v5',
            'OBSRVBL_IPFIX_PROBE_2_PORT': 'bogus',
            # No port - ignored
            'OBSRVBL_IPFIX_PROBE_3_TYPE': 'netflow-v5',
            # Invalid protocol - ignored
            'OBSRVBL_IPFIX_PROBE_4_TYPE': 'netflow-v5',
            'OBSRVBL_IPFIX_PROBE_4_PORT': '2055',
            'OBSRVBL_IPFIX_PROBE_4_PROTOCOL': 'scp',
            # Valid probe with a quirky source
            'OBSRVBL_IPFIX_PROBE_5_TYPE': 'netflow-v9',
            'OBSRVBL_IPFIX_PROBE_5_PORT': '9995',
            'OBSRVBL_IPFIX_PROBE_5_SOURCE': 'asa',
        }
        with patch.dict('ona_service.flowcap_config.environ', environ):
            self.flowcap_config.update()
            self.flowcap_config.write()

        with io.open(self.ipfix_conf, 'rt') as infile:
            actual = infile.read()

        expected = (
            'probe S0 netflow-v5\n'
            '  listen-on-port 2055\n'
            '  protocol udp\n'
            'end probe\n'
            '\n'
            'probe S5 netflow-v9\n'
            '  listen-on-port 9995\n'
            '  protocol udp\n'
            '  quirks firewall-event zero-packets\n'
            'end probe\n'
            '\n'
        )
        self.assertEqual(actual, expected)

    def test_yaf(self):
        environ = {
            # YAF is enabled
            'OBSRVBL_YAF_CAPTURER': 'true',
            'OBSRVBL_PNA_IFACES': 'eth0 eth1',
            # Valid probe
            'OBSRVBL_IPFIX_PROBE_0_TYPE': 'netflow-v5',
            'OBSRVBL_IPFIX_PROBE_0_PORT': '2055',
        }
        with patch.dict('ona_service.flowcap_config.environ', environ):
            self.flowcap_config.update()
            self.flowcap_config.write()

        with io.open(self.ipfix_conf, 'rt') as infile:
            actual = infile.read()

        expected = (
            'probe S0 netflow-v5\n'
            '  listen-on-port 2055\n'
            '  protocol udp\n'
            'end probe\n'
            '\n'
            'probe eth0 ipfix\n'
            '  listen-on-port 4739\n'
            '  protocol tcp\n'
            'end probe\n'
            '\n'
            'probe eth1 ipfix\n'
            '  listen-on-port 4740\n'
            '  protocol tcp\n'
            'end probe\n'
            '\n'
        )
        self.assertEqual(actual, expected)
