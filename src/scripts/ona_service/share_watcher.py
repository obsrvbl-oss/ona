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
import io
import logging

from os import fchmod, getenv, remove
from os.path import join
from random import choice, randrange
from string import digits, letters, punctuation
from sys import exit

# local
from service import Service
from log_watcher import LogNode
from utils import get_ip, send_observations, utc


FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

OBSERVATION_TYPE = 'share_watcher_v1'
POLL_SECONDS = 60
DEFAULT_SHARE_DIR = '/opt/obsrvbl-ona/share/'
DEFAULT_SHARE_FILE = 'README.txt'
CHARACTERS = digits + letters + punctuation + ' '
AUDIT_LOG_PATH = '/var/log/samba_audit.log'


class SambaAuditLogNode(LogNode):
    def __init__(self, *args, **kwargs):
        self.parsed_data = []
        super(SambaAuditLogNode, self).__init__(*args, **kwargs)

    def flush_data(self, data, *args, **kwargs):
        self.data.extend(data)

        for line in self.data:
            # Date Time Hostname Client IP|Client name|Host IP|Operation|Other
            line = line.strip()
            if not line:
                continue
            line = [x.strip() for x in line.rsplit(':', 1)[1].split('|', 5)]
            line_dict = {
                'client_ip': line[0],
                'client_hostname': line[1],
                'server_ip': line[2],
                'operation': line[3],
                'status': line[4],
                'argument': line[5],
            }
            self.parsed_data.append(line_dict)


class ShareWatcher(Service):
    def __init__(self, *args, **kwargs):
        log_path = kwargs.pop('log_path', AUDIT_LOG_PATH)
        kwargs.setdefault('poll_seconds', POLL_SECONDS)
        super(ShareWatcher, self).__init__(*args, **kwargs)

        self.share_dir = getenv('OBSRVBL_SHARE_DIR', DEFAULT_SHARE_DIR)
        self.share_file = getenv('OBSRVBL_SHARE_FILE', DEFAULT_SHARE_FILE)
        self.file_path = join(self.share_dir, self.share_file)

        # If we're in read only mode, track what's in the file currently.
        # The Samba audit log will be empty, so don't bother tracking it.
        if getenv('OBSRVBL_SHARE_READ_ONLY', 'false') == 'true':
            self.contents = self._read_contents()
            log_path = '/dev/null'
            self.source_ip = getenv('OBSRVBL_SHARE_IP')
        # If we're in read-write mode, dynamically generate a file and monitor
        # the Samba audit log
        else:
            try:
                remove(self.file_path)
            except (OSError, IOError):
                pass

            data = self._generate_contents()
            with io.open(self.file_path, 'wb') as outfile:
                outfile.write(data.encode('ascii'))
                fchmod(outfile.fileno(), 0o666)

            self.contents = self._read_contents()

            self.source_ip = get_ip()

        self.log_node = SambaAuditLogNode(
            log_type='samba_audit', api=self.api, log_path=log_path
        )

    def _generate_contents(self):
        line_count = randrange(1, 20 + 1)
        all_lines = []
        for i in xrange(line_count):
            char_count = randrange(1, 79 + 1)
            line = ''.join(choice(CHARACTERS) for __ in xrange(char_count))
            all_lines.append(line)

        return '\n'.join(all_lines)

    def _read_contents(self):
        try:
            with io.open(self.file_path, 'rb') as infile:
                return infile.read()
        except (IOError, OSError):
            logging.error('Error when reading %s', self.file_path)
            return None

    def execute(self, now=None):
        if now:
            now = now.replace(tzinfo=utc)

        if self._read_contents() == self.contents:
            return

        self.log_node.check_data(now)

        observation_data = {
            'source': self.source_ip,
            'time': now.isoformat(),
            'connected_ip': None,
            'connected_hostname': None,
            'operation': None,
            'argument': self.share_file,
        }
        if not self.log_node.parsed_data:
            all_observations = [observation_data.copy()]
        else:
            all_observations = []
            for line in self.log_node.parsed_data:
                obs = observation_data.copy()
                obs['connected_ip'] = line['client_ip']
                obs['connected_hostname'] = line['client_hostname']
                obs['operation'] = line['operation']
                obs['argument'] = line['argument']
                all_observations.append(obs)

        send_observations(
            api=self.api,
            obs_type=OBSERVATION_TYPE,
            obs_data=all_observations,
            now=now,
            suffix='share-watcher',
        )

        # Bail out; the supervisor should restart everything
        exit()


if __name__ == '__main__':
    ShareWatcher().run()
