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
# python builtins
import logging
import os
from tempfile import NamedTemporaryFile

# local
from ona_service.api import requests
from ona_service.service import Service

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

K8S_CA_CERT_PATH = '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'
K8S_TOKEN_PATH = '/var/run/secrets/kubernetes.io/serviceaccount/token'

DATA_TYPE = 'logs'
ENV_POD_NAME = 'OBSRVBL_POD_NAME'
ENV_KUBERNETES_LABEL = 'OBSRVBL_KUBERNETES_LABEL'
DEFAULT_KUBERNETES_LABEL = 'obsrvbl-ona'
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

        # Label for the pods in the daemonset
        self.k8s_label = os.environ.get(
            ENV_KUBERNETES_LABEL, DEFAULT_KUBERNETES_LABEL
        )

        self.match_hostname = (
            requests.packages.urllib3.connection.match_hostname
        )

        kwargs['poll_seconds'] = POLL_SECONDS
        super().__init__(*args, **kwargs)

    def _read_if_exists(self, *args, **kwargs):
        # Pass *args and **kwargs to io.open. Read the file handle and return
        # its data. If the file doesn't exist, return None.
        try:
            with open(*args, **kwargs) as infile:
                return infile.read()
        except OSError:
            return None

    def _get_headers(self):
        return {
            'Authorization': 'Bearer {}'.format(self.k8s_token),
            'Accept': 'application/json',
        }

    def _should_update(self):
        # We query the Kubernetes API server to see what other instances
        # of this service are running, using the `labelSelector` filter.
        # If we're the first one in the list (lexicographically), we will
        # continue on. Otherwise we'll go back to sleep and check later.
        this_pod_name = os.environ[ENV_POD_NAME]

        url = 'https://{}:{}/api/v1/pods/'.format(self.k8s_host, self.k8s_port)
        params = {'labelSelector': 'name={}'.format(self.k8s_label)}
        get_kwargs = {
            'url': url,
            'headers': self._get_headers(),
            'params': params,
            'verify': self.k8s_ca_cert_path,
        }

        # Make the request and parse the response
        resp = requests.get(**get_kwargs)
        resp.raise_for_status()
        pod_data = resp.json()

        # Pull out the names of the nodes running this application
        all_pods = []
        for item in pod_data.get('items', []):
            metadata = item.get('metadata', {})
            pod_name = metadata.get('name')
            if pod_name:
                all_pods.append(pod_name)

        # If we are the first one, we win the election
        all_pods.sort()
        if all_pods and (all_pods[0] == this_pod_name):
            return True

        # Otherwise we cede to the other pods
        logging.info(
            'This pod (%s) will not do the API query: %s',
            this_pod_name,
            ''.join(all_pods[:1])
        )
        return False

    def _send_update(self, now):
        # Talk to the Kubernetes API server discovered from the environment
        url = 'https://{}:{}/api/v1/pods/'.format(self.k8s_host, self.k8s_port)
        get_kwargs = {
            'url': url,
            'headers': self._get_headers(),
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
            should_update = self._should_update()
        except Exception:
            logging.exception('Error determining pod update instructions')
            should_update = False

        if should_update:
            try:
                self._send_update(now)
            except Exception:
                logging.exception('Error updating pod data')


if __name__ == '__main__':
    watcher = KubernetesWatcher()
    watcher.run()
