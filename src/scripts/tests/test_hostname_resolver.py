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
import io
import json
import signal

from subprocess import CalledProcessError
from unittest import TestCase

from mock import call, patch, MagicMock

from ona_service.hostname_resolver import (
    ENV_HOSTNAME_DNS,
    ENV_HOSTNAME_NETBIOS,
    gethostbyaddr,
    HostnameResolver,
    nmblookup,
    resolve_host_names,
)

PATCH_PATH = 'ona_service.hostname_resolver.{}'
DNS_RESOLUTIONS = {'10.1.1.1': 'test_1', '192.168.1.12': 'test_2'}
NETBIOS_RESOLUTIONS = {'192.0.2.1': 'test_3', '192.168.1.12': 'test_2.bogus'}


class HostnameResolverTest(TestCase):
    def test_gethostbyaddr(self):
        self.assertEqual(gethostbyaddr('127.0.0.1'), 'localhost')
        self.assertIsNone(gethostbyaddr('127.0.0.256'))
        self.assertIsNone(gethostbyaddr('bogus'))

    @patch(PATCH_PATH.format('subprocess.check_output'), autospec=True)
    def test_nmblookup(self, mock_check_output):
        mock_check_output.return_value = (
            'Ignoring unknown parameter "server role"\n'
            'Looking up status of 192.0.2.1\n'
            '\tWRONG           <00> -         M <OFFLINE>\n'
            '\tWKSOBSR01       <00> -         M <ACTIVE> \n'
            '\tON              <00> - <GROUP> M <ACTIVE> \n'
            '\tON              <1c> - <GROUP> M <ACTIVE> \n'
            '\tWKSOBSR01       <20> -         M <ACTIVE> \n'
            '\n\tMAC Address = 02-04-01-01-04-02\n'
            '\n'
        )
        self.assertEqual(nmblookup('192.0.2.1'), 'wksobsr01')
        mock_check_output.assert_called_once_with(
            'timeout 1s nmblookup -A 192.0.2.1'.split()
        )

    @patch(PATCH_PATH.format('subprocess.check_output'), autospec=True)
    def test_nmblookup_fail(self, mock_check_output):
        mock_check_output.return_value = (
            'Ignoring unknown parameter "server role"\n'
            'Looking up status of 192.0.2.1\n'
            'No reply from 192.0.2.1\n\n'
        )
        self.assertIsNone(nmblookup('192.0.2.1'))

        mock_check_output.side_effect = CalledProcessError(None, None)
        self.assertIsNone(nmblookup('192.0.2.1'))

    @patch(PATCH_PATH.format('sleep'), autospec=True)
    def test_resolve_host_names(self, mock_sleep):
        resolvers = [DNS_RESOLUTIONS.get, NETBIOS_RESOLUTIONS.get]
        ips = ['10.1.1.1', '192.168.1.12', '192.0.2.1', '198.51.100.1']
        actual = resolve_host_names(ips, resolvers)
        expected = {
            '10.1.1.1': 'test_1',
            '192.168.1.12': 'test_2',
            '192.0.2.1': 'test_3',
            '198.51.100.1': None,
        }
        self.assertEqual(actual, expected)
        self.assertEqual(mock_sleep.call_args_list, [call(0.1)] * len(ips))

    @patch(PATCH_PATH.format('gethostbyaddr'), DNS_RESOLUTIONS.get)
    def test_execute(self):
        self.inst = HostnameResolver()
        self.inst.api = MagicMock()

        # Set up mock for api.get_data - what we are to retrieve
        ips = ['10.1.1.1', '192.168.1.12']
        self.inst.api.get_data.return_value.json.return_value = ips

        # Set up mock for api.send_file
        remote_path = 'file:///tmp/obsrvbl/hostnames/resolutions.json'
        output = {}

        def _send_file(data_type, path, now, suffix=None):
            with io.open(path, 'rb') as infile:
                output[index] = infile.read()

            return remote_path
        self.inst.api.send_file.side_effect = _send_file

        # Do the deed
        index = 0
        self.inst.execute()

        self.assertEqual(self.inst.api.send_file.call_count, 1)
        call_args, call_kwargs = self.inst.api.send_file.call_args
        self.assertEqual(call_args[0], 'hostnames')
        self.assertEqual(call_kwargs['suffix'], 'hosts')
        self.assertEqual(output[0], json.dumps(DNS_RESOLUTIONS))
        self.inst.api.send_signal.assert_called_once_with(
            'hostnames', {'path': remote_path}
        )

    @patch.dict(
        'os.environ',
        {ENV_HOSTNAME_DNS: 'false', ENV_HOSTNAME_NETBIOS: 'true'}
    )
    @patch(PATCH_PATH.format('subprocess.check_output'), autospec=True)
    def test_execute_netbios(self, mock_check_output):
        self.inst = HostnameResolver()
        self.inst.api = MagicMock()

        # Set up mock for api.get_data - what we are to retrieve
        ips = ['192.0.2.1', '192.168.1.12']
        self.inst.api.get_data.return_value.json.return_value = ips

        # Set up mock for api.send_file
        remote_path = 'file:///tmp/obsrvbl/hostnames/resolutions.json'
        output = {}

        def _send_file(data_type, path, now, suffix=None):
            with io.open(path, 'rb') as infile:
                output[index] = infile.read()

            return remote_path
        self.inst.api.send_file.side_effect = _send_file

        # Set up the resolver
        def _check_output(*popenargs, **kwargs):
            ip = popenargs[0][-1]
            if ip == '192.0.2.1':
                return '\tTEST_3 <00> - M <ACTIVE> \n'
            elif ip == '192.168.1.12':
                return '\tTEST_2.BOGUS <00> - M <ACTIVE> \n'
            raise CalledProcessError(None, None)
        mock_check_output.side_effect = _check_output

        # Do the deed
        index = 0
        self.inst.execute()

        self.assertEqual(self.inst.api.send_file.call_count, 1)
        call_args, call_kwargs = self.inst.api.send_file.call_args
        self.assertEqual(call_args[0], 'hostnames')
        self.assertEqual(call_kwargs['suffix'], 'hosts')
        self.assertEqual(output[0], json.dumps(NETBIOS_RESOLUTIONS))
        self.inst.api.send_signal.assert_called_once_with(
            'hostnames', {'path': remote_path}
        )

    @patch.dict('os.environ', {ENV_HOSTNAME_NETBIOS: 'true'})
    @patch(PATCH_PATH.format('gethostbyaddr'), DNS_RESOLUTIONS.get)
    @patch(PATCH_PATH.format('subprocess.check_output'), autospec=True)
    def test_execute_both(self, mock_check_output):
        self.inst = HostnameResolver()
        self.inst.api = MagicMock()

        # Set up mock for api.get_data - what we are to retrieve
        ips = ['192.0.2.1', '192.168.1.12', '10.1.1.1', '198.51.100.1']
        self.inst.api.get_data.return_value.json.return_value = ips

        # Set up mock for api.send_file
        remote_path = 'file:///tmp/obsrvbl/hostnames/resolutions.json'
        output = {}

        def _send_file(data_type, path, now, suffix=None):
            with io.open(path, 'rb') as infile:
                output[index] = infile.read()

            return remote_path
        self.inst.api.send_file.side_effect = _send_file

        # Set up the resolver
        def _check_output(*popenargs, **kwargs):
            ip = popenargs[0][-1]
            if ip == '192.0.2.1':
                return '\tTEST_3 <00> - M <ACTIVE> \n'
            elif ip == '192.168.1.12':
                return '\tTEST_2.BOGUS <00> - M <ACTIVE> \n'
            raise CalledProcessError(None, None)
        mock_check_output.side_effect = _check_output

        expected_resolutions = {
            '192.0.2.1': NETBIOS_RESOLUTIONS['192.0.2.1'],
            '192.168.1.12': NETBIOS_RESOLUTIONS['192.168.1.12'],
            '10.1.1.1': DNS_RESOLUTIONS['10.1.1.1'],
            '198.51.100.1': None,
        }

        # Do the deed
        index = 0
        self.inst.execute()

        self.assertEqual(self.inst.api.send_file.call_count, 1)
        call_args, call_kwargs = self.inst.api.send_file.call_args
        self.assertEqual(call_args[0], 'hostnames')
        self.assertEqual(call_kwargs['suffix'], 'hosts')
        self.assertEqual(output[0], json.dumps(expected_resolutions))
        self.inst.api.send_signal.assert_called_once_with(
            'hostnames', {'path': remote_path}
        )

    @patch.dict(
        'os.environ',
        {ENV_HOSTNAME_DNS: 'false', ENV_HOSTNAME_NETBIOS: 'false'}
    )
    def test_execute_no_resolvers(self):
        self.inst = HostnameResolver()
        self.inst.api = MagicMock()
        self.inst.api.get_data.return_value.json.return_value = []
        self.inst.execute()

        self.assertEqual(self.inst.api.send_file.call_count, 0)
        self.assertEqual(self.inst.api.send_signal.call_count, 0)

    def test_execute_no_ips(self):
        self.inst = HostnameResolver()
        self.inst.api = MagicMock()
        self.inst.api.get_data.return_value.json.return_value = []
        self.inst.execute()

        self.assertEqual(self.inst.api.send_file.call_count, 0)
        self.assertEqual(self.inst.api.send_signal.call_count, 0)

    def test_execute_error(self):
        self.inst = HostnameResolver()
        self.inst.api = MagicMock()
        self.inst.api.get_data.return_value.json.side_effect = ValueError
        self.inst.execute()

        self.assertEqual(self.inst.api.send_file.call_count, 0)
        self.assertEqual(self.inst.api.send_signal.call_count, 0)

    def test_service(self):
        self.inst = HostnameResolver()
        self.inst.api = MagicMock()
        self.inst.poll_seconds = 0

        def killer(signum, frame):
            self.inst.stop()
        signal.signal(signal.SIGALRM, killer)
        signal.alarm(1)
        self.inst.run()
