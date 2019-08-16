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

from os.path import join
from json import load as json_load, dumps
from shutil import rmtree
from unittest import TestCase
from urlparse import urlparse
from tempfile import mkdtemp

import requests
from mock import patch, MagicMock

from ona_service.kubernetes_watcher import KubernetesWatcher

PATCH_PATH = 'ona_service.kubernetes_watcher.{}'


GET_PODS_RESPONSE = {
    'kind': 'PodList',
    'apiVersion': 'v1',
    'metadata': {'selfLink': '/api/v1/pods/'},
    'items': [
        # All good - default namespace
        {
            'metadata': {'name': 'pod-01', 'namespace': 'default'},
            'status': {'podIP': '192.0.2.1'},
        },
        # All good - custom namespace
        {
            'metadata': {'name': 'pod-02', 'namespace': 'custom'},
            'status': {'podIP': '192.0.2.2'},
        },
        # Missing podIP
        {
            'metadata': {'name': 'pod-03', 'namespace': 'default'},
            'status': {},
        },
        # Missing namespace
        {
            'metadata': {'name': 'pod-04'},
            'status': {'podIP': '192.0.2.4'},
        },
        # Missing name
        {
            'metadata': {'namespace': 'bogus'},
            'status': {'podIP': '192.0.2.5'},
        },
        # Host networking
        {
            'metadata': {'name': 'pod-06', 'namespace': 'default'},
            'spec': {'nodeName': 'node-01', 'hostNetwork': True},
            'status': {'podIP': '192.0.2.6'},
        },
        # The kube-proxy
        {
            'metadata': {
                'name': 'kube-proxy-node-01', 'namespace': 'kube-system'
            },
            'spec': {'nodeName': 'node-01', 'hostNetwork': True},
            'status': {'podIP': '192.0.2.6'},
        },
    ],
}


class KubernetesWatchers(TestCase):
    def setUp(self):
        self.tempdir = mkdtemp()

        self.k8s_ca_cert_path = join(self.tempdir, 'ca.crt')
        with io.open(self.k8s_ca_cert_path, 'wt') as outfile:
            print('CA Certificate!', file=outfile)

        self.k8s_token_path = join(self.tempdir, 'token')
        with io.open(self.k8s_token_path, 'wt') as outfile:
            print('Token!', file=outfile)

    def tearDown(self):
        rmtree(self.tempdir)

    @patch(PATCH_PATH.format('requests.get'), autospec=True)
    def test_execute(self, mock_get):
        # Mock the API response, returning the test data
        def _get(url, params=None, **kwargs):
            from ona_service.kubernetes_watcher import requests as r
            host = urlparse(url).hostname
            r.packages.urllib3.connection.match_hostname({None: None}, host)

            resp = requests.Response()
            resp.status_code = 200
            resp.raw = io.BytesIO(dumps(GET_PODS_RESPONSE).encode('utf-8'))
            return resp

        mock_get.side_effect = _get

        # Intercept the upload, and check for expected output
        def _send_file(data_type, path, now, suffix=None):
            self.assertEqual(data_type, 'logs')
            with open(path, 'rt') as infile:
                actual = json_load(infile)

            self.assertEqual(actual, GET_PODS_RESPONSE)

            return 'file://{}/mock-ona_k8s-pods'.format(self.tempdir)

        # Emulate the k8s environment and run the service
        env = {
            'KUBERNETES_SERVICE_HOST': '127.0.0.1',
            'KUBERNETES_SERVICE_PORT': '8080',
            'K8S_CA_CERT_PATH': self.k8s_ca_cert_path,
            'KUBERNETES_TOKEN_PATH': self.k8s_token_path,
        }
        with patch.dict(PATCH_PATH.format('os.environ'), env):
            inst = KubernetesWatcher()
            inst.api = MagicMock(inst.api)
            inst.api.send_file.side_effect = _send_file
            inst.execute()

        inst.api.send_signal.assert_called_once_with(
            'logs',
            {
                'log_type': 'k8s-pods',
                'path': 'file://{}/mock-ona_k8s-pods'.format(self.tempdir),
            }
        )

    @patch(PATCH_PATH.format('requests.get'), autospec=True)
    def test_execute_bad_status(self, mock_get):
        # Mock the API response, returning an error
        def _get(url, params=None, **kwargs):
            resp = requests.Response()
            resp.status_code = 403
            resp.raw = io.BytesIO(dumps({}).encode('utf-8'))
            return resp

        mock_get.side_effect = _get

        # Emulate the k8s environment and run the service
        env = {
            'KUBERNETES_SERVICE_HOST': '127.0.0.1',
            'KUBERNETES_SERVICE_PORT': '8080',
            'K8S_CA_CERT_PATH': self.k8s_ca_cert_path,
            'KUBERNETES_TOKEN_PATH': self.k8s_token_path,
        }
        with patch.dict(PATCH_PATH.format('os.environ'), env):
            inst = KubernetesWatcher()
            inst.api = MagicMock(inst.api)
            inst.execute()

        # No Observable API calls should be made
        self.assertEqual(inst.api.call_count, 0)

    @patch(PATCH_PATH.format('requests.get'), autospec=True)
    def test_execute_missing_env(self, mock_get):
        # No API calls to Kubernetes or Observable should be made if there's
        # any missing environment variables
        base_env = {
            'KUBERNETES_SERVICE_HOST': '127.0.0.1',
            'KUBERNETES_SERVICE_PORT': '8080',
            'K8S_CA_CERT_PATH': self.k8s_ca_cert_path,
            'KUBERNETES_TOKEN_PATH': self.k8s_token_path,
        }
        for key in base_env.iterkeys():
            env = base_env.copy()
            env.pop(key)
            with patch.dict(PATCH_PATH.format('os.environ'), env):
                inst = KubernetesWatcher()
                inst.api = MagicMock(inst.api)
                inst.execute()
                self.assertEqual(mock_get.call_count, 0)
                self.assertEqual(inst.api.call_count, 0)
