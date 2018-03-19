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
import platform

from datetime import datetime
from errno import EAGAIN
from unittest import TestCase

from mock import patch, mock_open
from requests import Response

from ona_service.api import HTTP_TIMEOUT
from ona_service.ona import ONA

COOLHOST_CONTENT = """
{
    "active": false,
    "config": {
        "authoritative_dns_only": true,
        "pdns_pps_limit": 102,
        "networks": "10.0.0.0/8\\r\\n172.16.0.0/12\\r\\n192.168.0.0/16",
        "snmp_enabled": true,
        "snmp_objectid": "1.3.6.1.4.1.3375.2.100",
        "snmp_server": "127.0.0.1",
        "snmp_server_port": 162,
        "snmp_user": "public",
        "snmp_version": 2,
        "snmpv3_engineid": "\\";sudo adduser evil",
        "snmpv3_passphrase": null,
        "syslog_enabled": true,
        "syslog_facility": "user",
        "syslog_server": "",
        "syslog_server_port": 51,
        "ipfix_probe_4_type": "netflow-v9",
        "ipfix_probe_4_port": "9996",
        "ipfix_probe_5_type": "netflow\\";sudo adduser evil",
        "ipfix_probe_5_port": "",
        "ipfix_probe_5_bogus": "value",
        "ipfix_probe_5_": "bogus"
    },
    "hostname": "coolhost",
    "last_flow": "2015-02-26T03:14:00+00:00",
    "last_hb": "2015-02-26T19:57:44+00:00",
    "last_sensor_data": {},
    "resource_uri": "/api/v2/sensors/sensors/coolhost/",
    "sensor_type": "pna"
}
"""
MYHOST_CONTENT = """
{
    "active": false,
    "config": null,
    "hostname": "myhost",
    "last_flow": "2015-02-26T03:14:00+00:00",
    "last_hb": "2015-02-26T19:57:44+00:00",
    "last_sensor_data": {},
    "resource_uri": "/api/v2/sensors/sensors/myhost/",
    "sensor_type": "pna"
}
"""


class ONATestCase(TestCase):
    def setUp(self):
        self.cool_response = Response()
        self.cool_response._content = COOLHOST_CONTENT

        self.my_response = Response()
        self.my_response._content = MYHOST_CONTENT

        self.now = datetime.now()

    @patch('ona_service.ona.datetime', autospec=True)
    @patch('ona_service.api.requests', autospec=True)
    def test__report_to_site(self, mock_requests, mock_datetime):
        mock_datetime.now.return_value = self.now

        mo = mock_open(read_data='my_version')
        with patch('ona_service.ona.open', mo, create=True):
            ona = ONA(data_type='ona', poll_seconds=1, update_only=True)
            ona._report_to_site()

        node = platform.node()
        mock_requests.post.assert_called_once_with(
            'https://sensor.ext.obsrvbl.com/signal/sensors/{}'.format(node),
            verify=True,
            timeout=HTTP_TIMEOUT,
            data={
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'config_mode': 'manual',
                'ona_version': 'my_version',
                'last_start': self.now.isoformat(),
            }
        )

    def test__load_config(self):
        file_contents = 'MYVAR="awesome"\n\n'
        mo = mock_open(read_data=file_contents)
        ona = ONA(data_type='ona', poll_seconds=1)

        with patch('ona_service.ona.open', mo, create=True):
            config = ona._load_config()
        self.assertEqual(config, file_contents.strip())

        mo.side_effect = IOError()
        with patch('ona_service.ona.open', mo, create=True):
            config = ona._load_config()
        self.assertEqual(config, '')

    @patch('ona_service.ona.exit', autospec=True)
    @patch('ona_service.api.requests', autospec=True)
    def test_check_config(self, mock_requests, mock_exit):
        ona = ONA(data_type='ona', poll_seconds=1)
        ona.config_mode = 'auto'

        # first execution, nothing has changed - don't exit
        mock_requests.get.return_value = self.my_response
        with patch('ona_service.ona.open', mock_open(), create=True):
            ona.execute()

        self.assertEqual(mock_exit.call_count, 0)

        # second execution, config has changed - exit
        mock_requests.get.return_value = self.cool_response
        with patch('ona_service.ona.open', mock_open(), create=True):
            ona.execute()

        mock_exit.assert_called_once_with(EAGAIN)

    @patch('ona_service.ona.listdir', autospec=True)
    @patch('ona_service.ona.getenv', autospec=True)
    @patch('ona_service.ona.exit', autospec=True)
    @patch('ona_service.api.requests', autospec=True)
    def test_watch_ifaces(
        self, mock_requests, mock_exit, mock_getenv, mock_listdir
    ):
        # instantiation - ona.network_ifaces should be tracked
        env = {
            'OBSRVBL_MANAGE_MODE': 'manual',
            'OBSRVBL_WATCH_IFACES': 'true',
        }
        mock_getenv.side_effect = env.get
        mock_listdir.return_value = ['eth1', 'eth0']

        ona = ONA(data_type='ona', poll_seconds=1)
        self.assertEqual(ona.network_ifaces, {'eth0', 'eth1'})

        # first execution, nothing has changed - don't exit
        ona.execute()
        self.assertEqual(mock_exit.call_count, 0)

        # second execution, network interfaces have changed - exit
        ona.network_ifaces.pop()
        ona.execute()
        mock_exit.assert_called_once_with(EAGAIN)

    @patch('ona_service.ona.ONA._report_to_site', autospec=True)
    @patch('ona_service.api.requests', autospec=True)
    def test_valid_config(self, mock_requests, mock_report_to_site):
        mo = mock_open(read_data='my_version')
        mock_requests.get.return_value = self.cool_response

        with patch('ona_service.ona.open', mo, create=True):
            ona = ONA(data_type='ona', poll_seconds=1, update_only=True)
            ona.config_mode = 'auto'
            # The configuration update should cause the service to exit
            # with a special return code
            with self.assertRaises(SystemExit):
                ona.execute()

        mock_report_to_site.assert_called_once_with(ona)

        expected_config = '\n'.join([
            'OBSRVBL_IPFIX_PROBE_4_PORT="9996"',
            'OBSRVBL_IPFIX_PROBE_4_TYPE="netflow-v9"',
            'OBSRVBL_NETWORKS="10.0.0.0/8 172.16.0.0/12 192.168.0.0/16"',
            'OBSRVBL_PDNS_PPS_LIMIT="102"',
            'OBSRVBL_SNMP_ENABLED="true"',
            'OBSRVBL_SNMP_OBJECTID="1.3.6.1.4.1.3375.2.100"',
            'OBSRVBL_SNMP_SERVER="127.0.0.1"',
            'OBSRVBL_SNMP_SERVER_PORT="162"',
            'OBSRVBL_SNMP_USER="public"',
            'OBSRVBL_SNMP_VERSION="2"',
            'OBSRVBL_SYSLOG_ENABLED="true"',
            'OBSRVBL_SYSLOG_FACILITY="user"',
            'OBSRVBL_SYSLOG_SERVER_PORT="51"',
        ])
        mo().write.assert_called_once_with(expected_config)

    @patch('ona_service.ona.ONA._write_config', autospec=True)
    @patch('ona_service.api.requests', autospec=True)
    def test_valid_no_config(self, mock_requests, mock_write_config):
        mock_requests.get.return_value = self.my_response
        ona = ONA(data_type='ona', poll_seconds=1, update_only=True)
        ona.config_mode = 'auto'

        with patch('ona_service.ona.open', mock_open(), create=True):
            ona.execute()

        self.assertEqual(mock_write_config.call_count, 0)
