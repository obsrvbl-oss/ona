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
from __future__ import unicode_literals
import io
import logging
import os

from csv import DictWriter
from datetime import timedelta
from gzip import GzipFile
from tempfile import NamedTemporaryFile

from requests import post
from dateutil.parser import parse as dt_parse

from service import Service
from utils import timestamp, utcnow, utc

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

DATA_TYPE = 'syslog_ad'
ENV_ISE_NODE_NAME = 'OBSRVBL_ISE_NODE_NAME'
ENV_ISE_SERVER_NAME = 'OBSRVBL_ISE_SERVER_NAME'
ENV_ISE_PASSWORD = 'OBSRVBL_ISE_PASSWORD'
ENV_ISE_CLIENT_CERT = 'OBSRVBL_ISE_CLIENT_CERT'
ENV_ISE_CLIENT_KEY = 'OBSRVBL_ISE_CLIENT_KEY'
ENV_ISE_CA_CERT = 'OBSRVBL_ISE_CA_CERT'
OUTPUT_FIELDNAMES = [
    '_time',
    'Computer',
    'TargetUserName',
    'EventCode',
    'ComputerAddress',
    'ActiveDirectoryDomain',
]
POLL_SECONDS = 600
TICK_DELTA = timedelta(microseconds=1000)
URL_TEMPLATE = 'https://{}:8910/pxgrid/control/{}'


class IsePoller(Service):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('poll_seconds', POLL_SECONDS)
        super(IsePoller, self).__init__(*args, **kwargs)

        self.server_name = os.environ.get(ENV_ISE_SERVER_NAME, '')
        self.node_name = os.environ.get(ENV_ISE_NODE_NAME) or self.api.ona_name
        self.password = os.environ.get(ENV_ISE_PASSWORD, '')
        self.client_cert = os.environ.get(ENV_ISE_CLIENT_CERT, '')
        self.client_key = os.environ.get(ENV_ISE_CLIENT_KEY, '')
        self.ca_cert = os.environ.get(ENV_ISE_CA_CERT, '')

        self.last_poll = None

    def _validate_certificate(self, file_path, env_var):
        # The certificate file has to exist
        try:
            with io.open(file_path, 'rt', errors='ignore') as infile:
                first_line = infile.readline()
        except (IOError, OSError):
            logging.error('Could not open %s from %s', file_path, env_var)
            return False

        # Verify that the file probably contains a certificate
        if 'BEGIN CERTIFICATE' not in first_line:
            logging.error(
                'Invalid certificate at %s from %s', file_path, env_var
            )
            return False

        return True

    def _validate_client_key(self):
        # The client key has to exist
        try:
            with io.open(self.client_key, 'rt', errors='ignore') as infile:
                first_line = infile.readline()
        except (IOError, OSError):
            logging.error(
                'Could not open %s from %s',
                self.client_key,
                ENV_ISE_CLIENT_KEY
            )
            return False

        # Common failure: the client key must not be encrypted
        if 'BEGIN ENCRYPTED PRIVATE KEY' in first_line:
            logging.error(
                'The client key at %s from %s must be decrypted before use',
                self.client_key,
                ENV_ISE_CLIENT_KEY
            )
            return False

        # Verify that the client key is unencrypted
        if 'BEGIN RSA PRIVATE KEY' not in first_line:
            logging.error(
                'Invalid client key at %s from %s',
                self.client_key,
                ENV_ISE_CLIENT_KEY
            )
            return False

        return True

    def _validate_configuration(self):
        if not self.server_name:
            logging.error('%s is not set', ENV_ISE_SERVER_NAME)
            return False

        if not self._validate_certificate(
            self.client_cert, ENV_ISE_CLIENT_CERT
        ):
            return False

        if not self._validate_certificate(self.ca_cert, ENV_ISE_CLIENT_KEY):
            return False

        if not self._validate_client_key():
            return False

        return True

    def _pxgrid_request(self, url, json_data, password):
        response = post(
            url=url,
            json=json_data,
            auth=(self.node_name, password),
            headers={'Accept': 'application/json'},
            cert=(self.client_cert, self.client_key),
            verify=self.ca_cert,
        )
        response.raise_for_status()
        return response.json()

    def _activate(self):
        activate_url = URL_TEMPLATE.format(self.server_name, 'AccountActivate')
        activate_resp = self._pxgrid_request(activate_url, {}, self.password)
        if activate_resp.get('accountState') != 'ENABLED':
            return False

        return True

    def _lookup_service(self):
        lookup_url = URL_TEMPLATE.format(self.server_name, 'ServiceLookup')
        lookup_data = {'name': 'com.cisco.ise.session'}
        lookup_resp = self._pxgrid_request(
            lookup_url, lookup_data, self.password
        )
        service = lookup_resp['services'][0]
        peer_node_name = service['nodeName']
        base_url = service['properties']['restBaseUrl']

        return peer_node_name, base_url

    def _get_secret(self, peer_node_name):
        access_url = URL_TEMPLATE.format(self.server_name, 'AccessSecret')
        access_data = {'peerNodeName': peer_node_name}
        access_resp = self._pxgrid_request(
            access_url, access_data, self.password
        )
        secret = access_resp['secret']

        return secret

    def _query_sessions(self, base_url, start_dt, secret):
        query_url = '{}/{}'.format(base_url, 'getSessions')
        query_data = {'startTimestamp': start_dt.isoformat()}
        query_response = self._pxgrid_request(query_url, query_data, secret)
        sessions = query_response.get('sessions', [])

        return sessions

    def _normalize_sessions(self, sessions):
        for s in sessions:
            if s['state'] != 'AUTHENTICATED':
                continue

            if not s.get('ipAddresses', []):
                continue

            yield {
                '_time': timestamp(dt_parse(s['timestamp'])),
                'Computer': None,
                'TargetUserName': s['adNormalizedUser'],
                'EventCode': None,
                'ComputerAddress': s['ipAddresses'][0],
                'ActiveDirectoryDomain': s['adUserDomainName'],
            }

    def execute(self, now=None):
        # We use the call time to determine query parameters and for the
        # remote storage location.
        now = now or utcnow()
        now = now.replace(tzinfo=utc)
        self.last_poll = self.last_poll or now
        ts = now.replace(
            minute=(now.minute // 10) * 10, second=0, microsecond=0
        )

        # Check the configuration and display helpful error messages
        if not self._validate_configuration():
            logging.error('Invalid configuration, could not start')
            return

        # Activate the pxGrid session
        if not self._activate():
            logging.warning('Activate request failed')
            return

        # Get the session service information
        peer_node_name, base_url = self._lookup_service()
        secret = self._get_secret(peer_node_name)

        # Do the query (starting one tick after the last poll) and save the
        # most recent timestamp for next time.
        start_dt = self.last_poll + TICK_DELTA
        sessions = self._query_sessions(base_url, start_dt, secret)
        if not sessions:
            logging.info('No sessions since %s', self.last_poll)
            return

        # Normalize the data and send it out
        normalized_sessions = self._normalize_sessions(sessions)
        with NamedTemporaryFile() as f:
            with GzipFile(fileobj=f) as gz_f:
                writer = DictWriter(gz_f, fieldnames=OUTPUT_FIELDNAMES)
                writer.writeheader()
                writer.writerows(normalized_sessions)
            f.flush()

            remote_path = self.api.send_file(
                DATA_TYPE,
                f.name,
                ts,
                suffix='{:04}'.format(now.minute * 60 + now.second)
            )
            if remote_path is not None:
                data = {'path': remote_path, 'log_type': DATA_TYPE}
                self.api.send_signal('logs', data=data)

        # Save the last poll time
        self.last_poll = max(dt_parse(s['timestamp']) for s in sessions)


if __name__ == '__main__':
    IsePoller().run()
