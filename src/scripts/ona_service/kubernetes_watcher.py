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

DATA_TYPE = 'logs'
LOG_TYPE = 'k8s-pods'
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

    def _send_update(self, now):
        # Talk to the Kubernetes API server discovered from the environment
        url = 'https://{}:{}/api/v1/pods/'.format(self.k8s_host, self.k8s_port)
        headers = {
            'Authorization': 'Bearer {}'.format(self.k8s_token),
            'Accept': 'application/json',
        }
        get_kwargs = {
            'url': url,
            'headers': headers,
            'verify': self.k8s_ca_cert_path,
            'stream': True,
        }

        # Make the request, streaming the response into a temporary file
        with NamedTemporaryFile() as f, requests.get(**get_kwargs) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(1024):
                if chunk:
                    f.write(chunk)

            # Push out the received data
            f.seek(0)
            remote_path = self.api.send_file(
                DATA_TYPE, f.name, now, suffix=LOG_TYPE
            )
            if remote_path is not None:
                data = {
                    'path': remote_path,
                    'log_type': LOG_TYPE,
                }
                self.api.send_signal(DATA_TYPE, data)

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
            self._send_update(now)
        except Exception:
            logging.exception('Error getting pod data')


if __name__ == '__main__':
    watcher = KubernetesWatcher()
    watcher.run()
