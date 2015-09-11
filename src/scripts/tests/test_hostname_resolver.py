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
import json
import signal
import socket

from datetime import datetime
from unittest import TestCase

from mock import call, patch, Mock

from ona_service.hostname_resolver import (
    HostnameResolver,
    resolve_host_name,
    resolve_host_names
)


class HostnameResolverTest(TestCase):
    def setUp(self):
        pass

    @patch('ona_service.hostname_resolver.sleep')
    @patch('socket.gethostbyaddr')
    def test_resolve_host_names(self, mock_get_host, mock_sleep):
        mock_get_host.return_value = ('test', '')

        ips = ['10.1.1.1', '192.168.1.12']
        hosts = resolve_host_names(ips)

        self.assertEquals(hosts, {
            '10.1.1.1': 'test',
            '192.168.1.12': 'test'
        })
        self.assertEquals(mock_sleep.call_args_list, [
            call(0.1),
            call(0.1),
        ])

    @patch('socket.gethostbyaddr')
    def test_resolve_host_name_kaboom(self, mock_get_host):
        mock_get_host.side_effect = socket.herror

        host = resolve_host_name('bad ip')
        self.assertEquals(host, None)

    @patch('ona_service.api.Api.send_signal')
    @patch('ona_service.api.Api.send_file')
    @patch('ona_service.hostname_resolver.NamedTemporaryFile')
    def test_update_host_names(self, mock_tempfile, mock_upload, mock_signal):
        handle = Mock()
        handle.name = 'foobar'
        mock_tempfile.return_value.__enter__.return_value = handle
        mock_upload.return_value = 's3://blah/blah'

        hosts = ['host1', 'host2']
        time = datetime.utcnow()
        resolver = HostnameResolver()
        resolver._update_host_names(hosts, time)

        handle.write.assert_called_once_with(json.dumps(hosts))
        mock_upload.assert_called_once_with('hostnames', 'foobar', time,
                                            suffix='hosts')
        mock_signal.assert_called_once_with(
            'hostnames', {'path': mock_upload.return_value})

    @patch('ona_service.hostname_resolver.resolve_host_names')
    @patch('ona_service.hostname_resolver.HostnameResolver._update_host_names')
    @patch('ona_service.api.Api.get_data')
    def test_execute(self, mock_get_data, mock_update, mock_resolve):
        ips = ['1.2.3.4', '5.6.7.8']
        hosts = ['host1', 'host2']
        mock_get_data.return_value.json.return_value = ips
        mock_resolve.return_value = hosts

        resolver = HostnameResolver()
        resolver.execute()

        mock_get_data.assert_called_once_with('hostnames')
        mock_resolve.assert_called_once_with(ips)
        mock_update.assert_called_once_with(hosts, None)

    @patch('ona_service.hostname_resolver.resolve_host_names')
    @patch('ona_service.hostname_resolver.HostnameResolver._update_host_names')
    @patch('ona_service.api.Api.get_data')
    def test_execute_specify_date(self, mock_get_data, mock_update,
                                  mock_resolve):
        ips = ['1.2.3.4', '5.6.7.8']
        hosts = ['host1', 'host2']
        mock_get_data.return_value.json.return_value = ips
        mock_resolve.return_value = hosts

        time = datetime.utcnow()
        resolver = HostnameResolver()
        resolver.execute(time)

        mock_get_data.assert_called_once_with('hostnames')
        mock_resolve.assert_called_once_with(ips)
        mock_update.assert_called_once_with(hosts, time)

    @patch('ona_service.hostname_resolver.resolve_host_names')
    @patch('ona_service.hostname_resolver.HostnameResolver._update_host_names')
    @patch('ona_service.api.Api.get_data')
    def test_execute_no_ips(self, mock_get_data, mock_update, mock_resolve):
        ips = []
        mock_get_data.return_value.json.return_value = ips

        resolver = HostnameResolver()
        resolver.execute()

        mock_get_data.assert_called_once_with('hostnames')
        self.assertEquals(mock_resolve.call_args_list, [])
        self.assertEquals(mock_update.call_args_list, [])

    @patch('ona_service.hostname_resolver.resolve_host_names')
    @patch('ona_service.hostname_resolver.HostnameResolver._update_host_names')
    @patch('ona_service.api.Api.get_data')
    def test_execute_ipsplosion(self, mock_get_data, mock_update,
                                mock_resolve):
        mock_get_data.return_value.json.side_effect = ValueError

        resolver = HostnameResolver()
        resolver.execute()

        mock_get_data.assert_called_once_with('hostnames')
        self.assertEquals(mock_resolve.call_args_list, [])
        self.assertEquals(mock_update.call_args_list, [])

    @patch('ona_service.api.requests', autospec=True)
    def test_service(self, mock_requests):
        resolver = HostnameResolver()
        resolver.poll_seconds = 0

        def killer(signum, frame):
            resolver.stop()
        signal.signal(signal.SIGALRM, killer)
        signal.alarm(1)
        resolver.run()
