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

from datetime import datetime, timedelta
from collections import defaultdict
from csv import DictWriter
from gzip import open as gz_open
from json import dumps, loads
from os import environ, remove
from os.path import join, split
from shutil import copy
from tempfile import NamedTemporaryFile

# local
from nvzflow_reader import ENV_NVZFLOW_LOG_DIR, DEFAULT_NVZFLOW_LOG_DIR
from pusher import Pusher
from utils import utc

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

POLL_SECONDS = 30
MAX_HOSTNAME_AGE = timedelta(days=1)

CSV_HEADER = [
    'srcaddr',
    'dstaddr',
    'srcport',
    'dstport',
    'protocol',
    'bytes_in',
    'bytes_out',
    'start',
    'end',
]


class EndpointInfo(object):
    __slots__ = ['hostname', 'address', 'last_seen']

    def __init__(self):
        self.hostname = None
        self.address = None
        self.last_seen = datetime.now(utc)

    def update(self, item, now=None):
        if 'virtualStationName' in item:
            self.hostname = item['virtualStationName']

        if 'sourceIPv4Address' in item:
            self.address = item['sourceIPv4Address']
        elif 'sourceIPv6Address' in item:
            self.address = item['sourceIPv6Address']

        self.last_seen = now or datetime.now(utc)

    def __repr__(self):
        return '<EndpointInfo {}: {}>'.format(self.address, self.hostname)


class NVZFlowPusher(Pusher):
    """Combines NVZFlow data into 10 minute segments and send them to
    Observable Networks.
    """

    def __init__(self, *args, **kwargs):
        input_dir = environ.get(ENV_NVZFLOW_LOG_DIR, DEFAULT_NVZFLOW_LOG_DIR)
        for key, default in (
            ('file_fmt', 'nvzflow.log.%Y-%m-%d_%H-%M'),
            ('prefix_len', 28),
            ('data_type', 'csv'),
            ('input_dir', input_dir),
            ('poll_seconds', POLL_SECONDS),
        ):
            kwargs.setdefault(key, default)

        self.udid_map = defaultdict(EndpointInfo)
        self.tar_mode = 'w'
        super(NVZFlowPusher, self).__init__(*args, **kwargs)

    def _get_nvz_flows(self, file_path):
        # This is a generator that has a side effect. It yields the flows
        # that look like standard NetFlow, and updates the hostname mapping
        # for ones with extra host information.
        with io.open(file_path, 'rt') as infile:
            for line in infile:
                in_flow = loads(line)

                if 'nvzFlowUDID' in in_flow:
                    udid = in_flow['nvzFlowUDID']
                    self.udid_map[udid].update(in_flow)

                try:
                    out_flow = {
                        'srcaddr': (
                            in_flow.get('sourceIPv4Address') or
                            in_flow['sourceIPv6Address']
                        ),
                        'dstaddr': (
                            in_flow.get('destinationIPv4Address') or
                            in_flow['destinationIPv6Address']
                        ),
                        'srcport': in_flow['sourceTransportPort'],
                        'dstport': in_flow['destinationTransportPort'],
                        'protocol': in_flow['protocolIdentifier'],
                        'bytes_in': in_flow['nvzFlowL4ByteCountIn'],
                        'bytes_out': in_flow['nvzFlowL4ByteCountOut'],
                        'start': in_flow['flowStartSeconds'],
                        'end': in_flow['flowEndSeconds'],
                    }
                except KeyError:
                    continue
                else:
                    yield out_flow

    def _process_files(self, file_list):
        for file_path in file_list:
            file_dir, file_name = split(file_path)
            temp_path = join(file_dir, '{}.tmp'.format(file_name))
            copy(file_path, temp_path)
            try:
                all_rows = self._get_nvz_flows(temp_path)
                with gz_open(file_path, 'wt') as outfile:
                    writer = DictWriter(outfile, CSV_HEADER)
                    writer.writeheader()
                    writer.writerows(all_rows)
            finally:
                remove(temp_path)

    def _update_host_names(self, hostname_map, now):
        with NamedTemporaryFile() as f:
            f.write(dumps(hostname_map))
            f.seek(0)
            path = self.api.send_file('hostnames', f.name, now, suffix='hosts')
            if path is not None:
                data = {'path': path}
                self.api.send_signal('hostnames', data)

    def execute(self, now=None):
        super(NVZFlowPusher, self).execute(now=now)

        now = now or datetime.now(utc)
        now = now.astimezone(utc) if now.tzinfo else now.replace(tzinfo=utc)

        # Pull out the valid IP address-to-hostname mappings
        hostname_map = {}
        stale_entries = []
        for udid, endpoint in self.udid_map.iteritems():
            if now - endpoint.last_seen > MAX_HOSTNAME_AGE:
                stale_entries.append(udid)
            if (
                (endpoint.hostname is None) or
                (endpoint.hostname == '-') or
                (endpoint.address is None) or
                (endpoint.address == '0.0.0.0') or
                (endpoint.address == '::')
            ):
                continue
            hostname_map[endpoint.address] = endpoint.hostname

        # Remove the ones that haven't been seen in a while
        for udid in stale_entries:
            del self.hostname_map[udid]

        # Send out the mapping
        if hostname_map:
            self._update_host_names(hostname_map, now)


if __name__ == '__main__':
    pusher = NVZFlowPusher()
    pusher.run()
