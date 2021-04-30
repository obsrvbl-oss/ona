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
import io
from os.path import join
from json import load as json_load, dumps
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse

import requests

from ona_service.kubernetes_watcher import (
    ENV_POD_NAME,
    DEFAULT_KUBERNETES_LABEL,
    KubernetesWatcher,
)

PATCH_PATH = 'ona_service.kubernetes_watcher.{}'


GET_PODS_RESPONSE = {
    'kind': 'PodList',
    'apiVersion': 'v1',
    'metadata': {'selfLink': '/api/v1/pods/'},
    'items': [
        # The winner of the election
        {
            'metadata': {'name': 'obsrvbl-ona-01', 'namespace': 'default'},
            'spec': {'nodeName': 'node-01', 'hostNetwork': True},
        },
        # The loser of the election
        {
            'metadata': {'name': 'obsrvbl-ona-02', 'namespace': 'default'},
            'spec': {'nodeName': 'node-02', 'hostNetwork': True},
        },
        # Missing pod name, somehow
        {
            'metadata': {'namespace': 'default'},
        },
        # Missing metadata, somehow
        {
            'spec': {'hostNetwork': True},
        },
    ],
}


class KubernetesWatchers(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()

        self.k8s_ca_cert_path = join(self.temp_dir.name, 'ca.crt')
        with open(self.k8s_ca_cert_path, 'wt') as outfile:
            print('CA Certificate!', file=outfile, end='')

        self.k8s_token_path = join(self.temp_dir.name, 'token')
        with open(self.k8s_token_path, 'wt') as outfile:
            print('Token!', file=outfile, end='')

        self.test_env = {
            'KUBERNETES_SERVICE_HOST': '127.0.0.1',
            'KUBERNETES_SERVICE_PORT': '8080',
            'K8S_CA_CERT_PATH': self.k8s_ca_cert_path,
            'KUBERNETES_TOKEN_PATH': self.k8s_token_path,
            ENV_POD_NAME: 'obsrvbl-ona-01',
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch(PATCH_PATH.format('requests.get'), autospec=True)
    def test_execute(self, mock_get):
        # Mock the API response, returning the test data
        def _get(url, params=None, **kwargs):
            from ona_service.kubernetes_watcher import requests as r
            host = urlparse(url).hostname
            r.packages.urllib3.connection.match_hostname({None: None}, host)

            headers = kwargs['headers']
            self.assertEqual(headers['Authorization'], 'Bearer Token!')
            self.assertEqual(headers['Accept'], 'application/json')

            resp = requests.Response()
            resp.status_code = 200
            resp.raw = io.BytesIO(dumps(GET_PODS_RESPONSE).encode('utf-8'))
            return resp

        mock_get.side_effect = _get

        # Intercept the upload, and check for expected output
        def _send_file(data_type, path, now, suffix=None):
            self.assertEqual(data_type, 'logs')
            with open(path) as infile:
                actual = json_load(infile)

            self.assertEqual(actual, GET_PODS_RESPONSE)

            return 'file://{}/mock-ona_k8s-pods'.format(self.temp_dir.name)

        # Emulate the k8s environment and run the service
        with patch.dict(PATCH_PATH.format('os.environ'), self.test_env):
            inst = KubernetesWatcher()
            inst.api = MagicMock(inst.api)
            inst.api.send_file.side_effect = _send_file
            inst.execute()

        # The first call should be filtered; the second shouldn't be filtered.
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(
            mock_get.call_args_list[0][1].get('params'),
            {'labelSelector': 'name={}'.format(DEFAULT_KUBERNETES_LABEL)},
        )
        self.assertEqual(
            mock_get.call_args_list[1][1].get('params'),
            None
        )

        # The site signal should indicate the type and path
        inst.api.send_signal.assert_called_once_with(
            'logs',
            {
                'log_type': 'k8s-pods',
                'path': (
                    'file://{}/mock-ona_k8s-pods'.format(self.temp_dir.name)
                )
            }
        )

    @patch(PATCH_PATH.format('requests.get'), autospec=True)
    def test_should_not_execute(self, mock_get):
        # When the hostname isn't the first, we shouldn't do any further
        # querying.

        # Mock the API response, returning the test data
        def _get(url, params=None, **kwargs):
            from ona_service.kubernetes_watcher import requests as r
            host = urlparse(url).hostname
            r.packages.urllib3.connection.match_hostname({None: None}, host)

            self.assertTrue(params)

            resp = requests.Response()
            resp.status_code = 200
            resp.raw = io.BytesIO(dumps(GET_PODS_RESPONSE).encode('utf-8'))
            return resp

        mock_get.side_effect = _get

        # Emulate the k8s environment and run the service
        with patch.dict(PATCH_PATH.format('os.environ'), self.test_env):
            inst = KubernetesWatcher()
            inst.api = MagicMock(inst.api)
            inst.execute()

        inst.api.send_file.assert_not_called()
        inst.api.send_signal.assert_not_called()

    @patch(PATCH_PATH.format('requests.get'), autospec=True)
    def test_execute_bad_check(self, mock_get):
        # Mock the API response, returning an error
        def _get(url, params=None, **kwargs):
            resp = requests.Response()

            resp.status_code = 403
            resp.raw = io.BytesIO(dumps({}).encode('utf-8'))
            return resp

        mock_get.side_effect = _get

        # Emulate the k8s environment and run the service
        with patch.dict(PATCH_PATH.format('os.environ'), self.test_env):
            inst = KubernetesWatcher()
            inst.api = MagicMock(inst.api)
            inst.execute()

        # Since the initial check failed, no second GET should be made.
        # No Observable API calls should be made
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(inst.api.call_count, 0)

    @patch(PATCH_PATH.format('requests.get'), autospec=True)
    def test_execute_bad_update(self, mock_get):
        # Mock the API response, returning an error
        def _get(url, params=None, **kwargs):
            resp = requests.Response()

            if params:
                resp = requests.Response()
                resp.status_code = 200
                resp.raw = io.BytesIO(dumps(GET_PODS_RESPONSE).encode('utf-8'))
            else:
                resp.status_code = 403
                resp.raw = io.BytesIO(dumps({}).encode('utf-8'))
            return resp

        mock_get.side_effect = _get

        # Emulate the k8s environment and run the service
        with patch.dict(PATCH_PATH.format('os.environ'), self.test_env):
            inst = KubernetesWatcher()
            inst.api = MagicMock(inst.api)
            inst.execute()

        # Since the initial check succeeded, a second GET should be made.
        # No Observable API calls should be made
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(inst.api.call_count, 0)

    @patch(PATCH_PATH.format('requests.get'), autospec=True)
    def test_execute_missing_env(self, mock_get):
        # No API calls to Kubernetes or Observable should be made if there's
        # any missing environment variables
        for key in self.test_env.keys():
            env = self.test_env.copy()
            env.pop(key)
            with patch.dict(PATCH_PATH.format('os.environ'), env):
                inst = KubernetesWatcher()
                inst.api = MagicMock(inst.api)
                inst.execute()
                self.assertEqual(mock_get.call_count, 0)
                self.assertEqual(inst.api.call_count, 0)
