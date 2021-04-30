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
from os.path import join
from subprocess import CalledProcessError, STDOUT
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ona_service.flowcap_config import (
    ENV_IPFIX_CONF,
    ENV_IPSET_UDP_CONF,
    ENV_IPSET_TCP_CONF,
    FlowcapConfig,
    IPSET_PATH,
    IPTABLES_PATH,
)


class FlowcapConfigTestCase(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.ipfix_conf = join(self.temp_dir.name, 'sensor.conf')
        self.ipset_udp_conf = join(self.temp_dir.name, 'netflow-udp.ipset')
        self.ipset_tcp_conf = join(self.temp_dir.name, 'netflow-tcp.ipset')

        environ = {
            ENV_IPFIX_CONF: self.ipfix_conf,
            ENV_IPSET_UDP_CONF: self.ipset_udp_conf,
            ENV_IPSET_TCP_CONF: self.ipset_tcp_conf,
        }
        with patch.dict('ona_service.flowcap_config.environ', environ):
            self.flowcap_config = FlowcapConfig()

    def tearDown(self):
        self.temp_dir.cleanup()

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
            # Somebody duplicated the port / protocol; ignore
            'OBSRVBL_IPFIX_PROBE_6_TYPE': 'netflow-v9',
            'OBSRVBL_IPFIX_PROBE_6_PORT': '9995',
            'OBSRVBL_IPFIX_PROBE_6_PROTOCOL': 'udp',
        }
        with patch.dict('ona_service.flowcap_config.environ', environ):
            self.flowcap_config.update()
            self.flowcap_config.write()

        with open(self.ipfix_conf) as infile:
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

        with open(self.ipfix_conf) as infile:
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

    @patch('ona_service.flowcap_config.check_output', autospec=True)
    def test_should_add(self, mock_check_output):
        rule_args = [
            'INPUT',
            '-p', 'udp',
            '-m', 'set',
            '--match-set', 'netflow-udp', 'dst',
            '-j', 'ACCEPT'
        ]
        for side_effect, expected in [
            # No existing rule, go ahead
            (
                CalledProcessError(1, '', output='iptables: Bad rule'),
                True
            ),
            # Wrong message, don't add
            (
                CalledProcessError(1, '', output='iptables: Brad rule'),
                False
            ),
            # Wrong error code, don't add
            (
                CalledProcessError(3, '', output='iptables: Bad rule'),
                False
            ),
            # Different type of error, don't add
            (
                OSError,
                False
            ),
            # Rule exists - don't add
            (
                lambda *args, **kwargs: None,
                False
            ),
        ]:
            # The method should return the expected result
            mock_check_output.side_effect = side_effect
            actual = self.flowcap_config._should_add(rule_args)
            self.assertEqual(actual, expected)

            # iptables should concatenate the -C command the the rule args
            self.assertEqual(mock_check_output.call_count, 1)
            actual_command = ' '.join(mock_check_output.call_args[0][0])
            expected_command = (
                'sudo -n {} -C INPUT -p udp -m set --match-set netflow-udp dst'
                ' -j ACCEPT'
            ).format(IPTABLES_PATH)
            self.assertEqual(actual_command, expected_command)

            # We need to check stderr to see if rules weren't there
            self.assertEqual(
                mock_check_output.call_args[1],
                {'stderr': STDOUT, 'encoding': 'utf-8', 'errors': 'ignore'},
            )

            mock_check_output.reset_mock()

    @patch('ona_service.flowcap_config.call', autospec=True)
    @patch('ona_service.flowcap_config.check_output', autospec=True)
    def test_configure_iptables(self, mock_check_output, mock_call):
        # iptables returns 1 when the rule does not exist
        mock_check_output.side_effect = CalledProcessError(
            1, '', output='iptables: Bad rule'
        )

        environ = {
            # YAF is enabled, but local only
            'OBSRVBL_YAF_CAPTURER': 'true',
            'OBSRVBL_PNA_IFACES': 'eth0 eth1',
            # Valid probe 1
            'OBSRVBL_IPFIX_PROBE_0_TYPE': 'netflow-v5',
            'OBSRVBL_IPFIX_PROBE_0_PORT': '2055',
            # Valid probe 2
            'OBSRVBL_IPFIX_PROBE_1_TYPE': 'netflow-v9',
            'OBSRVBL_IPFIX_PROBE_1_PORT': '9995',
            'OBSRVBL_IPFIX_PROBE_1_PROTOCOL': 'tcp',
        }
        with patch.dict('ona_service.flowcap_config.environ', environ):
            self.flowcap_config.update()
            self.flowcap_config.configure_iptables()

        # Check configuration files
        with open(self.ipset_udp_conf) as infile:
            actual = infile.read().splitlines()
            expected = [
                'create netflow-udp bitmap:port range 1024-65535',
                'add netflow-udp 2055',
            ]
            self.assertEqual(actual, expected)

        with open(self.ipset_tcp_conf) as infile:
            actual = infile.read().splitlines()
            expected = [
                'create netflow-tcp bitmap:port range 1024-65535',
                'add netflow-tcp 9995',
            ]
            self.assertEqual(actual, expected)

        # Check firewall manipulation
        expected_commands = [
            (
                'sudo -n {} restore -exist -file {}'
            ).format(IPSET_PATH, self.ipset_udp_conf),
            (
                'sudo -n {} -A INPUT -p udp -m set '
                '--match-set netflow-udp dst -j ACCEPT'
            ).format(IPTABLES_PATH),
            (
                'sudo -n {} restore -exist -file {}'
            ).format(IPSET_PATH, self.ipset_tcp_conf),
            (
                'sudo -n {} -A INPUT -p tcp -m set '
                '--match-set netflow-tcp dst -j ACCEPT'
            ).format(IPTABLES_PATH),
        ]
        actual_commands = []
        for call_args, call_kwargs in mock_call.call_args_list:
            actual_commands.append(' '.join(call_args[0]))

        self.assertEqual(expected_commands, actual_commands)

    @patch('ona_service.flowcap_config.call', autospec=True)
    @patch('ona_service.flowcap_config.check_output', autospec=True)
    def test_configure_iptables_duplicate(self, mock_check_output, mock_call):
        # iptables returns 0 when the rule exists
        mock_check_output.side_effect = lambda *args, **kwargs: None

        environ = {
            # Valid probe 1
            'OBSRVBL_IPFIX_PROBE_0_TYPE': 'netflow-v5',
            'OBSRVBL_IPFIX_PROBE_0_PORT': '2055',
            # Valid probe 2
            'OBSRVBL_IPFIX_PROBE_1_TYPE': 'netflow-v9',
            'OBSRVBL_IPFIX_PROBE_1_PORT': '9995',
            'OBSRVBL_IPFIX_PROBE_1_PROTOCOL': 'tcp',
        }
        with patch.dict('ona_service.flowcap_config.environ', environ):
            self.flowcap_config.update()
            self.flowcap_config.configure_iptables()

        # Check configuration files
        with open(self.ipset_udp_conf) as infile:
            actual = infile.read().splitlines()
            expected = [
                'create netflow-udp bitmap:port range 1024-65535',
                'add netflow-udp 2055',
            ]
            self.assertEqual(actual, expected)

        with open(self.ipset_tcp_conf) as infile:
            actual = infile.read().splitlines()
            expected = [
                'create netflow-tcp bitmap:port range 1024-65535',
                'add netflow-tcp 9995',
            ]
            self.assertEqual(actual, expected)

        # The ipsets get updated, but the rules are not added to the chain
        expected_commands = [
            (
                'sudo -n {} restore -exist -file {}'
            ).format(IPSET_PATH, self.ipset_udp_conf),
            (
                'sudo -n {} restore -exist -file {}'
            ).format(IPSET_PATH, self.ipset_tcp_conf),
        ]
        actual_commands = []
        for call_args, call_kwargs in mock_call.call_args_list:
            actual_commands.append(' '.join(call_args[0]))

        self.assertEqual(expected_commands, actual_commands)
