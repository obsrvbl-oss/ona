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

# python builtins
import io
import json
import logging
import os
from tempfile import NamedTemporaryFile

# local
from api import requests
from service import Service

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

K8S_CA_CERT_PATH = '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'
K8S_TOKEN_PATH = '/var/run/secrets/kubernetes.io/serviceaccount/token'

DATA_TYPE = 'hostnames'
POLL_SECONDS = 3600


class KubernetesWatcher(Service):
    def __init__(self, *args, **kwargs):
        # Kubernetes API endpoint
        self.k8s_host = os.environ.get('KUBERNETES_SERVICE_HOST')
        self.k8s_port = os.environ.get('KUBERNETES_SERVICE_PORT')

        # Kubernetes CA certificate
        self.k8s_ca_cert_path = os.environ.get(
            'K8S_CA_CERT_PATH', K8S_CA_CERT_PATH
        )

        # Kubernetes authentication token
        k8s_token_path = os.environ.get(
            'KUBERNETES_TOKEN_PATH', K8S_TOKEN_PATH
        )
        self.k8s_token = self._read_if_exists(k8s_token_path)

        self.match_hostname = (
            requests.packages.urllib3.connection.match_hostname
        )

        kwargs.update({
            'poll_seconds': POLL_SECONDS,
        })
        super(KubernetesWatcher, self).__init__(*args, **kwargs)

    def _read_if_exists(self, *args, **kwargs):
        # Pass *args and **kwargs to io.open. Read the file handle and return
        # its data. If the file doesn't exist, return None.
        try:
            with io.open(*args, **kwargs) as infile:
                return infile.read()
        except (IOError, OSError):
            return None

    def _send_update(self, resolved, now):
        with NamedTemporaryFile() as f:
            f.write(json.dumps(resolved))
            f.seek(0)
            path = self.api.send_file(DATA_TYPE, f.name, now, suffix='hosts')
            if path is not None:
                data = {'path': path}
                self.api.send_signal(DATA_TYPE, data)

    def _get_pods(self):
        # Hit the k8s API server for pods in all namespaces
        url = 'https://{}:{}/api/v1/pods/'.format(self.k8s_host, self.k8s_port)
        headers = {
            'Authorization': 'Bearer {}'.format(self.k8s_token),
            'Accept': 'application/json',
        }
        resp = requests.get(url, headers=headers, verify=self.k8s_ca_cert_path)
        resp.raise_for_status()
        pod_data = resp.json()

        pod_ip_map = {}
        cluster_ip_map = {}
        for item in pod_data.get('items', []):
            metadata = item.get('metadata', {})
            pod_name = metadata.get('name')
            pod_namespace = metadata.get('namespace')

            status = item.get('status', {})
            pod_ip = status.get('podIP')

            spec = item.get('spec', {})
            host_network = spec.get('hostNetwork', False)
            node_name = spec.get('nodeName')

            # Skip incomplete entries
            if (not pod_name) or (not pod_namespace) or (not pod_ip):
                continue

            # For pods that share the node's address, report that address
            if host_network:
                if node_name:
                    cluster_ip_map[pod_ip] = node_name
            # Otherwise, report pod-name.pod-namespace
            else:
                pod_ip_map[pod_ip] = '{}.{}'.format(pod_name, pod_namespace)

        pod_ip_map.update(cluster_ip_map)
        return pod_ip_map

    def _set_hostname_match(self):
        # Ensure that the hostname validates. This is required for certain
        # versions of Python 2.7 and requests/urllib3.
        def _match_hostname(cert, hostname):
            try:
                self.match_hostname(cert, hostname)
            except Exception:
                if hostname != self.k8s_host:
                    raise

        requests.packages.urllib3.connection.match_hostname = _match_hostname

    def _check_access(self):
        # All the access variables must be set, and the CA cert path
        # must exist
        check_vars = (
            self.k8s_host, self.k8s_port, self.k8s_ca_cert_path, self.k8s_token
        )
        if any(x is None for x in check_vars):
            return False

        return os.path.exists(self.k8s_ca_cert_path)

    def execute(self, now=None):
        if not self._check_access():
            logging.error('Missing Kubernetes connection parameters')
            return

        self._set_hostname_match()
        try:
            resolved = self._get_pods()
        except Exception:
            logging.exception('Error getting pod data')
            return

        if not resolved:
            logging.error('No mappings were found')
            return

        self._send_update(resolved, now)


if __name__ == '__main__':
    watcher = KubernetesWatcher()
    watcher.run()
