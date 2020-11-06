#  Copyright 2019 Observable Networks
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
import os

from datetime import datetime
from json import dumps
from os.path import join
from shutil import rmtree
from tempfile import mkdtemp
from unittest import TestCase

from mock import patch, MagicMock
from requests import Response

from ona_service.ise_poller import (
    ENV_ISE_CA_CERT,
    ENV_ISE_CLIENT_CERT,
    ENV_ISE_CLIENT_KEY,
    ENV_ISE_NODE_NAME,
    ENV_ISE_PASSWORD,
    ENV_ISE_SERVER_NAME,
    IsePoller,
    OUTPUT_FIELDNAMES,
    SEND_FILE_TYPE,
    SENSORDATA_TYPE,
    TICK_DELTA,
)
from ona_service.utils import gunzip_bytes, utc

PATCH_PATH = 'ona_service.ise_poller.{}'.format


class IsePollerTests(TestCase):
    def setUp(self):
        self.temp_dir = mkdtemp()

        # Write dummy certificate and key files
        self.client_cert = join(self.temp_dir, 'client_cert')
        with io.open(self.client_cert, 'wt') as outfile:
            print('-----BEGIN CERTIFICATE-----', file=outfile)
            print('-----END CERTIFICATE-----', file=outfile)

        self.client_key = join(self.temp_dir, 'client_key')
        with io.open(self.client_key, 'wt') as outfile:
            print('-----BEGIN RSA PRIVATE KEY-----', file=outfile)
            print('-----END RSA PRIVATE KEY-----', file=outfile)

        self.ca_cert = join(self.temp_dir, 'ca_cert')
        with io.open(self.ca_cert, 'wt') as outfile:
            print('-----BEGIN CERTIFICATE-----', file=outfile)
            print('-----END CERTIFICATE-----', file=outfile)

        self.now = datetime(2019, 1, 29, 12, 34, 0, tzinfo=utc)
        self.expected_headers = {'Accept': 'application/json'}

    def tearDown(self):
        rmtree(self.temp_dir, ignore_errors=True)

    def _get_instance(self, **env):
        base_env = {
            ENV_ISE_SERVER_NAME: 'localhost',
            ENV_ISE_NODE_NAME: '',
            ENV_ISE_PASSWORD: '',
            ENV_ISE_CLIENT_CERT: self.client_cert,
            ENV_ISE_CLIENT_KEY: self.client_key,
            ENV_ISE_CA_CERT: self.ca_cert,
        }
        base_env.update(env)

        with patch.dict(PATCH_PATH('os.environ'), base_env):
            inst = IsePoller()
            inst.api = MagicMock()

        return inst

    @patch(PATCH_PATH('post'), autospec=True)
    def test_execute_missing(self, mock_post):
        # Simulate missing variables or wrong file paths - no server calls
        # should be attempted.
        for env_var in [
            ENV_ISE_SERVER_NAME,
            ENV_ISE_CLIENT_CERT,
            ENV_ISE_CLIENT_KEY,
            ENV_ISE_CA_CERT,
        ]:
            inst = self._get_instance(**{env_var: ''})
            inst.api.get_data.return_value.json.return_value = {}
            inst.execute()
            self.assertEqual(mock_post.call_count, 0)

        # Simulate wrong contents in the certificate and key files - no
        # server calls should be attempted.
        for file_path in [self.client_cert, self.client_key, self.ca_cert]:
            with io.open(file_path, 'wb') as outfile:
                outfile.write(b'\x80-----BEGIN NONSENSE-----\n')
                outfile.write(b'\x80-----END NONSENSE-----\n')

            inst = self._get_instance()
            inst.api.get_data.return_value.json.return_value = {}
            inst.execute()
            self.assertEqual(mock_post.call_count, 0)

    @patch(PATCH_PATH('post'), autospec=True)
    def test_rewrite_urls(self, mock_post):
        # When the server name is an IP address...
        inst = self._get_instance(**{ENV_ISE_SERVER_NAME: '127.0.0.1'})
        inst.api.get_data.return_value.json.return_value = {}

        data = {
            'accountState': 'ENABLED',
            'services': [
                {
                    'nodeName': 'service-node',
                    'properties': {
                        'restBaseUrl': 'https://localhost:8241'
                    },
                },
            ],
            'secret': 'service-node-secret',
        }
        activate_resp = Response()
        activate_resp._content = dumps(data).encode('utf-8')
        activate_resp.status_code = 200
        mock_post.return_value = activate_resp

        # ...The rewrite_urls flag gets set
        inst.execute()
        self.assertTrue(inst.rewrite_urls)

        # ...And URLs get re-written, preserving ports
        actual_urls = {c[1]['url'] for c in mock_post.call_args_list}
        expected_urls = {
            'https://127.0.0.1:8910/pxgrid/control/AccountActivate',
            'https://127.0.0.1:8910/pxgrid/control/ServiceLookup',
            'https://127.0.0.1:8910/pxgrid/control/AccessSecret',
            'https://127.0.0.1:8241/getSessions'
        }
        self.assertEqual(actual_urls, expected_urls)
        self.assertFalse(any(c[1]['verify'] for c in mock_post.call_args_list))

    @patch(PATCH_PATH('post'), autospec=True)
    def test_execute_server(self, mock_post):
        # No manual configuration is set
        env_vars = {
            ENV_ISE_SERVER_NAME: '',
            ENV_ISE_CLIENT_CERT: '',
            ENV_ISE_CLIENT_KEY: '',
            ENV_ISE_CA_CERT: '',
        }
        inst = self._get_instance(**env_vars)

        # The server supplies configuration
        server_resp = {
            'config': {
                'ISE_SERVER_NAME': 'localhost:8000',
                'ISE_PASSWORD': 'ona-password',
                'ISE_NODE_NAME': 'ona-node',
                'ISE_DATA_CLIENT_CERT': (
                    '-----BEGIN CERTIFICATE-----\r\n'
                    '-----END CERTIFICATE-----\r\n'
                ),
                'ISE_DATA_CLIENT_KEY': (
                    '-----BEGIN RSA PRIVATE KEY-----\r\n'
                    '-----END RSA PRIVATE KEY-----\r\n'
                ),
                'ISE_DATA_CA_CERT': (
                    '-----BEGIN CERTIFICATE-----\r\n'
                    '-----END CERTIFICATE-----\r\n'
                ),
            }
        }
        inst.api.get_data.return_value.json.return_value = server_resp

        # The service should start, and the server's data should be saved
        inst.execute()
        self.assertEqual(mock_post.call_count, 1)

        for attr, key in (
            ('server_name', 'ISE_SERVER_NAME'),
            ('password', 'ISE_PASSWORD'),
            ('node_name', 'ISE_NODE_NAME'),
        ):
            self.assertEqual(getattr(inst, attr), server_resp['config'][key])

        for attr, key in (
            ('client_cert', 'ISE_DATA_CLIENT_CERT'),
            ('client_key', 'ISE_DATA_CLIENT_KEY'),
            ('ca_cert', 'ISE_DATA_CA_CERT'),
        ):
            file_path = getattr(inst, attr)
            self.assertEqual(oct(os.stat(file_path).st_mode)[-3:], '600')
            with open(file_path, 'rt') as f:
                self.assertEqual(f.read(), server_resp['config'][key])

    @patch(PATCH_PATH('post'), autospec=True)
    def test_exceute(self, mock_post):
        # Intercept the ISE API calls
        def _post(url, data=None, json=None, **kwargs):
            resp = Response()
            resp.status_code = 200

            # All calls require the same headers and certificates
            self.assertEqual(kwargs['headers'], self.expected_headers)
            self.assertEqual(
                kwargs['cert'], (self.client_cert, self.client_key)
            )
            self.assertEqual(kwargs['verify'], self.ca_cert)

            if url.startswith('https://localhost:8910/pxgrid/control'):
                # Control requests use a static password
                self.assertEqual(kwargs['auth'], ('ona-node', 'ona-password'))

                # Account activation
                if url.endswith('/AccountActivate'):
                    expected_input = {}
                    output_json = {'accountState': 'ENABLED'}
                # Service lookup
                elif url.endswith('/ServiceLookup'):
                    expected_input = {'name': 'com.cisco.ise.session'}
                    output_json = {
                        'services': [
                            {
                                'nodeName': 'service-node',
                                'properties': {
                                    'restBaseUrl': 'https://localhost:8241'
                                },
                            },
                        ]
                    }
                # Secret request
                if url.endswith('/AccessSecret'):
                    expected_input = {'peerNodeName': 'service-node'}
                    output_json = {'secret': 'service-node-secret'}
            # The peer node answers the Get Sessions requests
            elif url == ('https://localhost:8241/getSessions'):
                # The peer node uses the secret for authorization
                self.assertEqual(
                    kwargs['auth'], ('ona-node', 'service-node-secret')
                )

                expected_input = {
                    'startTimestamp': (self.now + TICK_DELTA).isoformat()
                }
                output_json = {
                    'sessions': [
                        # Wrong state
                        {
                            'state': 'DISCONNECTED',
                            'timestamp': '2019-01-29T12:34:01.100-06:00',
                        },
                        # No IP addresses
                        {
                            'state': 'AUTHENTICATED',
                            'timestamp': '2019-01-29T12:34:01.100-06:00',
                        },
                        # No adUserDomainName
                        {
                            'state': 'AUTHENTICATED',
                            'ipAddresses': ['192.0.2.0', '192.0.2.1'],
                            'timestamp': '2019-01-29T12:34:01.100-06:00',
                            'adNormalizedUser': 'some-user\ufffd\ufffd',
                        },
                        # Valid
                        {
                            'state': 'AUTHENTICATED',
                            'ipAddresses': ['192.0.2.0', '192.0.2.1'],
                            'timestamp': '2019-01-29T12:34:01.100-06:00',
                            'adNormalizedUser': 'some-user\ufffd\ufffd',
                            'adUserDomainName': u'some-domain\ufffd\ufffd',
                        },
                        # Valid
                        {
                            'state': 'AUTHENTICATED',
                            'ipAddresses': ['192.0.2.0', '192.0.2.1'],
                            'timestamp': '2019-01-29T12:34:01.100-06:00',
                            'adNormalizedUser': '00:00:00:00:00:00',
                            'adUserDomainName': u'some-domain\ufffd\ufffd',
                        },
                    ]
                }
                self.assertEqual(kwargs['headers'], self.expected_headers)

            else:
                resp.status_code = 404

            self.assertEqual(json, expected_input)
            resp._content = dumps(output_json).encode('utf-8')
            return resp

        mock_post.side_effect = _post

        # Intercept the file upload
        output = {}

        def send_file(data_type, path, now, suffix=None):
            self.assertEqual(data_type, SEND_FILE_TYPE)
            with io.open(path, 'rb') as infile:
                output[index] = infile.read()

            return 'file:///tmp/ise_data.csv.gz'

        # Get an IsePoller instance
        inst = self._get_instance(
            OBSRVBL_ISE_NODE_NAME='ona-node',
            OBSRVBL_ISE_PASSWORD='ona-password',
        )
        inst.api.send_file.side_effect = send_file

        # Do the deed
        index = 0
        inst.execute(now=self.now)
        actual = gunzip_bytes(output[index]).splitlines()
        expected = [
            ','.join(OUTPUT_FIELDNAMES),
            '1548786841,,some-user,,192.0.2.0,some-domain',
        ]
        self.assertEqual(actual, expected)
        inst.api.send_signal.assert_called_once_with(
            data_type='sensordata',
            data={
                'timestamp': self.now.isoformat(),
                'data_type': SENSORDATA_TYPE,
                'data_path': 'file:///tmp/ise_data.csv.gz',
            }
        )
