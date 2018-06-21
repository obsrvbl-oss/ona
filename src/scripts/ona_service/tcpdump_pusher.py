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
from glob import iglob
import logging
from os import remove
from os.path import join
from subprocess import call

# local
from service import Service
from utils import create_dirs


class TcpdumpPusher(Service):
    """
    Captures packets with a tcpdump process and periodically uploads them.
    """
    def __init__(self, *args, **kwargs):
        self.data_type = kwargs['data_type']
        self.pcap_dir = kwargs.pop('pcap_dir')
        create_dirs(self.pcap_dir)
        super(TcpdumpPusher, self).__init__(*args, **kwargs)

    def compress_pcaps(self):
        """
        Compresses the finished pcap files in the capture directory.
        """
        # Skip the file with the most recent timestamp; it's not finished yet.
        glob_pattern = join(self.pcap_dir, '{}_*.pcap'.format(self.data_type))
        for file_path in sorted(iglob(glob_pattern))[:-1]:
            logging.info('Compressing %s', file_path)
            rc = call(['gzip', '-f', file_path])
            if rc:
                logging.error('Error compressing %s: %s', file_path, rc)

    def push_files(self, now):
        """
        Sends out the compressed pcap files in the capture directory, then
        removes them.
        """
        logging.info('Pushing .pcap.gz files')
        ret = []
        ts = now.replace(
            minute=(now.minute // 10) * 10,
            second=0,
            microsecond=0
        )

        glob_pattern = join(
            self.pcap_dir, '{}_*.pcap.gz'.format(self.data_type)
        )
        for i, file_path in enumerate(sorted(iglob(glob_pattern))):
            remote_path = self.api.send_file(
                self.data_type, file_path, ts, suffix='{:04}'.format(i)
            )
            ret.append(remote_path)
            remove(file_path)

        return ret

    def execute(self, now=None):
        self.compress_pcaps()
        return self.push_files(now)
