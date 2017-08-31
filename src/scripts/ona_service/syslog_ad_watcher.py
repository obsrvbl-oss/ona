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
from __future__ import division, print_function, unicode_literals

# python builtins
import csv
import logging

from datetime import datetime
from gzip import GzipFile
from os import getenv
from tempfile import NamedTemporaryFile

# local
from service import Service
from log_watcher import LogNode
from utils import utcoffset, utcnow, timestamp

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

DATA_TYPE = 'syslog_ad'
DEFAULT_AD_PATH = '/var/log/remote-ad.log'
OUTPUT_FIELDNAMES = [
    '_time',
    'Computer',
    'TargetUserName',
    'EventCode',
    'ComputerAddress',
]
POLL_SECONDS = 60
SKIP_SIDS = {'S-1-5-7', 'S-1-5-18'}


def _process_multiline(entry):
    # Given a multi-line Active Directory log entry, returns a dictionary with
    # the associated data.
    D = {}
    __, date_str, summary = entry[0].split('|', 2)
    summary_fields = summary.split('\t')
    D['Received time'] = date_str
    D['Event Code'] = summary_fields[1]

    lines = (x for x in entry[1:] if x)
    for line in lines:
        fields = [x for x in line.split('\t')]
        collapsed_fields = [x for x in fields if x]
        if fields[0].endswith(':') and len(collapsed_fields) == 1:
            section = collapsed_fields[0].rstrip(':')
            D[section] = {}
        elif fields[0] and len(collapsed_fields) == 2:
            key = collapsed_fields[0].rstrip(':')
            value = collapsed_fields[1]
            D[key] = value
        elif not fields[0] and len(collapsed_fields) == 2:
            key = collapsed_fields[0].rstrip(':')
            value = collapsed_fields[1]
            D[section][key] = value
        else:
            continue
    return D


def _process_oneline(entry):
    # Given a single-line Active Directory log entry, returns a dictionary
    # with the assocated data.
    __, date_str, rest = entry.split('|', 2)
    fields = rest.split(',')
    event_code = fields[1].strip()
    D = {
        'Security ID': None,
        'Account Name': None,
        'Workstation Name': None,
        'Source Network Address': None,
        'Event Code': event_code,
        'Received time': date_str,
    }
    data = fields[-2]
    for item in data.split('   '):
        item = item.strip().split(':', 1)
        if len(item) != 2:
            continue
        key, value = [x.strip() for x in item]
        if (key not in D) or (not value):
            continue
        D[key] = value

    return D


class RemoteADLogNode(LogNode):
    def __init__(self, *args, **kwargs):
        self.parsed_data = []
        self.entry = []
        self.is_complete = False
        kwargs.setdefault('encoding', 'cp1252')
        super(RemoteADLogNode, self).__init__(*args, **kwargs)

    def flush_data(self, data, now, compress=True):
        for line in data:
            # One-line format
            if line.startswith('obsrvbl_remote-ad_oneline|'):
                D_entry = _process_oneline(line)
                self.parsed_data.append(D_entry)
                continue

            # Multi-line format:
            # As long as this isn't a new line, add to the current entry
            if not line.startswith('obsrvbl_remote-ad|'):
                self.entry.append(line.rstrip())
            # When we see a new line start, process the current entry (if
            # we saw the whole thing)
            else:
                if self.is_complete:
                    D_entry = _process_multiline(self.entry)
                    if D_entry is not None:
                        self.parsed_data.append(D_entry)
                # Start a new entry
                self.entry = [line.rstrip()]
                self.is_complete = True


class SyslogADWatcher(Service):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('poll_seconds', POLL_SECONDS)
        super(SyslogADWatcher, self).__init__(*args, **kwargs)

        self.utcoffset = utcoffset()
        self.domain_suffix = getenv('OBSRVBL_DOMAIN_SUFFIX', '')
        self.data_type = DATA_TYPE
        self.log_node = RemoteADLogNode(
            log_type=self.data_type,
            api=self.api,
            log_path=getenv('OBSRVBL_SYSLOG_AD_PATH', DEFAULT_AD_PATH)
        )

    def _get_interesting_events(self, events):
        for D_event in events:
            # Look for new session events
            event_id = D_event.get('Event Code')
            if event_id != '4624':
                continue

            # Skip internal events
            new_logon = D_event.get('New Logon', D_event)
            security_id = new_logon.get('Security ID')
            if security_id in SKIP_SIDS:
                continue

            yield D_event

    def _get_formatted_events(self, events):
        for D_event in events:
            # Fall back to parent dict if sub-dicts are not available
            network_info = D_event.get('Network Information', D_event)
            account_info = D_event.get('New Logon', D_event)

            # The time format is set in rsyslog
            received_time = datetime.strptime(
                D_event['Received time'], '%Y-%m-%d %H:%M'
            )
            _time = timestamp(received_time) - self.utcoffset

            computer = network_info.get('Workstation Name')
            if computer is not None:
                computer = (computer + self.domain_suffix).lower()

            # Skip local service accounts ending with $
            user_name = account_info.get('Account Name', '')
            if user_name.endswith('$'):
                continue

            event_code = D_event['Event Code']
            ip_address = network_info.get('Source Network Address', '')

            yield (_time, computer, user_name, event_code, ip_address)

    def execute(self, now=None):
        now = now or utcnow()
        ts = now.replace(
            minute=(now.minute // 10) * 10, second=0, microsecond=0
        )

        self.log_node.check_data(now)
        all_events = self.log_node.parsed_data
        if not all_events:
            return
        interesting_events = self._get_interesting_events(all_events)
        formatted_events = set(self._get_formatted_events(interesting_events))
        with NamedTemporaryFile() as f:
            with GzipFile(fileobj=f) as gz_f:
                writer = csv.writer(gz_f)
                writer.writerow(OUTPUT_FIELDNAMES)
                writer.writerows(formatted_events)
            f.flush()

            remote_path = self.api.send_file(
                self.data_type,
                f.name,
                ts,
                suffix='{:04}'.format(now.minute * 60 + now.second)
            )
            if remote_path is not None:
                data = {'path': remote_path, 'log_type': self.data_type}
                self.api.send_signal('logs', data=data)

        self.log_node.parsed_data = []


if __name__ == '__main__':
    SyslogADWatcher().run()
