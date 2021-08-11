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
import json
import logging
import os

from datetime import timedelta
from gzip import open as gz_open
from os import makedirs
from os.path import join
from secrets import token_hex
from tempfile import gettempdir, NamedTemporaryFile
from urllib.parse import urlparse

from requests import post
from dateutil.parser import parse as dt_parse

from ona_service.service import Service
from ona_service.utils import exploded_ip, is_ip_address, utc, utcnow

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

SEND_FILE_TYPE = 'ise-events'
SENSORDATA_TYPE = 'ise-events'

ENV_ISE_NODE_NAME = 'OBSRVBL_ISE_NODE_NAME'
ENV_ISE_SERVER_NAME = 'OBSRVBL_ISE_SERVER_NAME'
ENV_ISE_SERVER_PORT = 'OBSRVBL_ISE_SERVER_PORT'
ENV_ISE_PASSWORD = 'OBSRVBL_ISE_PASSWORD'
ENV_ISE_CLIENT_CERT = 'OBSRVBL_ISE_CLIENT_CERT'
ENV_ISE_CLIENT_KEY = 'OBSRVBL_ISE_CLIENT_KEY'
ENV_ISE_CA_CERT = 'OBSRVBL_ISE_CA_CERT'

POLL_SECONDS = 600
TICK_DELTA = timedelta(microseconds=1000)
URL_TEMPLATE = 'https://{}:{}/pxgrid/control/{}'


class IsePoller(Service):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('poll_seconds', POLL_SECONDS)
        super().__init__(*args, **kwargs)

        self.server_name = os.environ.get(ENV_ISE_SERVER_NAME, '')
        self.server_port = int(os.environ.get(ENV_ISE_SERVER_PORT, '8910'))
        self.node_name = os.environ.get(ENV_ISE_NODE_NAME) or self.api.ona_name
        self.password = os.environ.get(ENV_ISE_PASSWORD, '')
        self.client_cert = os.environ.get(ENV_ISE_CLIENT_CERT, '')
        self.client_key = os.environ.get(ENV_ISE_CLIENT_KEY, '')
        self.ca_cert = os.environ.get(ENV_ISE_CA_CERT, '')

        self.last_poll = None
        self.cert_dir = join(gettempdir(), 'ise_poller')
        self.rewrite_urls = False

    def _validate_certificate(self, file_path, env_var):
        # The certificate file has to exist
        try:
            with open(file_path, errors='ignore') as infile:
                first_line = infile.readline()
        except OSError:
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
            with open(self.client_key, errors='ignore') as infile:
                first_line = infile.readline()
        except OSError:
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

    def _write_remote_data(self, file_path, data):
        # Touch a file, change its permissions so others can't read it, and
        # then write to it.
        with open(file_path, mode='wt') as f:
            pass

        os.chmod(file_path, 0o600)

        with open(file_path, mode='wt') as f:
            f.write(data)

    def _get_remote_configuration(self):
        # Query the server for ISE configuration
        endpoint = 'sensors/{}'.format(self.api.ona_name)
        try:
            resp = self.api.get_data(endpoint).json()['config']
        except Exception:
            return

        # Save the values from the response
        for key, attr in (
            ('ISE_SERVER_NAME', 'server_name'),
            ('ISE_SERVER_PORT', 'server_port'),
            ('ISE_PASSWORD', 'password'),
            ('ISE_NODE_NAME', 'node_name'),
        ):
            if key in resp:
                setattr(self, attr, resp[key])

        # Write the retrieved certificated data to the temporary directory.
        makedirs(self.cert_dir, exist_ok=True)
        for key, attr in (
            ('ISE_DATA_CLIENT_CERT', 'client_cert'),
            ('ISE_DATA_CLIENT_KEY', 'client_key'),
            ('ISE_DATA_CA_CERT', 'ca_cert'),
        ):
            data = resp.get(key, '')
            file_path = join(self.cert_dir, attr)
            setattr(self, attr, file_path)
            self._write_remote_data(file_path, data)

    def _pxgrid_request(self, url, json_data, password):
        verify = self.ca_cert
        if self.rewrite_urls:
            parsed_url = urlparse(url)
            netloc = '{}:{}'.format(self.server_name, parsed_url.port)
            url = parsed_url._replace(netloc=netloc).geturl()
            verify = False

        response = post(
            url=url,
            json=json_data,
            auth=(self.node_name, password),
            headers={'Accept': 'application/json'},
            cert=(self.client_cert, self.client_key),
            verify=verify,
        )
        response.raise_for_status()
        return response.json()

    def _activate(self):
        activate_url = URL_TEMPLATE.format(
            self.server_name, self.server_port, 'AccountActivate'
        )
        activate_resp = self._pxgrid_request(activate_url, {}, self.password)
        if activate_resp.get('accountState') != 'ENABLED':
            return False

        return True

    def _lookup_service(self):
        lookup_url = URL_TEMPLATE.format(
            self.server_name, self.server_port, 'ServiceLookup'
        )
        lookup_data = {'name': 'com.cisco.ise.session'}
        lookup_resp = self._pxgrid_request(
            lookup_url, lookup_data, self.password
        )
        all_services = lookup_resp.get('services')
        if not all_services:
            logging.warning('No services for com.cisco.ise.session')
            return

        for service in all_services:
            peer_node_name = service['nodeName']
            base_url = service['properties']['restBaseUrl']

            yield peer_node_name, base_url

    def _get_secret(self, peer_node_name):
        access_url = URL_TEMPLATE.format(
            self.server_name, self.server_port, 'AccessSecret'
        )
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

    @staticmethod
    def _normalize_session(session, ingest_dt):
        if 'ipAddresses' in session:
            try:
                session['ipAddresses_0'] = exploded_ip(
                    session['ipAddresses'][0]
                )
            except Exception:
                pass

        if 'nasIpAddress' in session:
            address = session['nasIpAddress']
            try:
                address = exploded_ip(address)
            except Exception:
                pass
            session['nasIpAddress'] = address

        session['ingestTimestamp'] = ingest_dt.isoformat()

        return json.dumps(session)

    def execute(self, now=None):
        # We use the call time to determine query parameters and for the
        # remote storage location.
        now = now or utcnow()
        now = now.replace(tzinfo=utc)
        self.last_poll = self.last_poll or now
        ts = now.replace(
            minute=(now.minute // 10) * 10, second=0, microsecond=0
        )

        # Check the saved configuration. If it's not complete, try to retrieve
        # configuration from the server.
        if not self._validate_configuration():
            self._get_remote_configuration()
            if not self._validate_configuration():
                logging.error('Invalid configuration, could not start')
                return

        self.rewrite_urls = is_ip_address(self.server_name)

        # Activate the pxGrid session
        if not self._activate():
            logging.warning('Activate request failed')
            return

        # Do the query (starting one tick after the last poll) and save the
        # most recent timestamp for next time.
        start_dt = self.last_poll + TICK_DELTA

        # Query each session service source for new events
        sessions = []
        for peer_node_name, base_url in self._lookup_service():
            secret = self._get_secret(peer_node_name)
            sessions += self._query_sessions(base_url, start_dt, secret)

        if not sessions:
            logging.info('No sessions since %s', self.last_poll)
            return

        with NamedTemporaryFile() as f:
            with gz_open(f, 'wt', newline='') as gz_f:
                for line in sessions:
                    print(self._normalize_session(line, now), file=gz_f)
            f.flush()

            remote_path = self.api.send_file(
                SEND_FILE_TYPE,
                f.name,
                ts,
                prefix=now.strftime('%Y-%m-%d-%H-%M-%S'),
                suffix='{}.jsonl.gz'.format(token_hex(4))
            )
            if remote_path is not None:
                data = {
                    'timestamp': now.isoformat(),
                    'data_type': SENSORDATA_TYPE,
                    'data_path': remote_path,
                }
                self.api.send_signal(data_type='sensordata', data=data)

        # Save the last poll time
        self.last_poll = max(dt_parse(s['timestamp']) for s in sessions)


if __name__ == '__main__':
    IsePoller().run()
