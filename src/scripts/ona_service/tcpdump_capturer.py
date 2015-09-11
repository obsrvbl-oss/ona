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
from subprocess import call, Popen

# local
from service import Service
from utils import create_dirs


class TcpdumpCapturer(Service):
    """
    Captures packets with a tcpdump process and periodically uploads them.
    """
    def __init__(self, *args, **kwargs):
        self.bpf_filter = kwargs.pop('bpf_filter')
        self.data_type = kwargs['data_type']
        self.capture_iface = kwargs.pop('capture_iface')
        self.capture_seconds = kwargs.pop('capture_seconds')
        self.pcap_dir = kwargs.pop('pcap_dir')
        self.pps_limit = kwargs.pop('pps_limit')

        self.capture_process = None
        create_dirs(self.pcap_dir)
        self.packet_limit = self.capture_seconds * self.pps_limit

        super(TcpdumpCapturer, self).__init__(*args, **kwargs)

    def check_capture(self):
        """
        Returns True if there is a tcpdump capture running and False otherwise.
        """
        # Capture has not yet been initialized
        if self.capture_process is None:
            logging.info('tcpdump has not yet been initialized')
            return False

        # Capture has been initialized, but exited prematurely
        rc = self.capture_process.poll()
        if rc is not None:
            logging.error('tcpdump exited with return code: %s', rc)
            return False

        # Capture is still running
        logging.info('tcdpump is still running')
        return True

    def start_capture(self):
        """
        Starts a tcpdump capture process.
        """
        pcap_path = join(self.pcap_dir, '{}_%s.pcap'.format(self.data_type))

        # Set up a tcpdump capture
        tcpdump_args = [
            'sudo',  # Capture as root
            '/usr/sbin/tcpdump',
            '-w', pcap_path,  # Output to file
            '-i', self.capture_iface,  # Listen on the given interface
            '-s', '0',  # Capture the whole packet
            '-c', '{}'.format(self.packet_limit),  # Exit after this many
            '-G', '{}'.format(self.capture_seconds),  # File switching interval
            '-U',  # Don't wait to write packets
            '-Z', 'obsrvbl_ona',  # Drop privileges
            self.bpf_filter
        ]
        self.capture_process = Popen(tcpdump_args)

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
        ts = now.replace(
            minute=(now.minute // 10) * 10,
            second=0,
            microsecond=0
        )

        glob_pattern = join(
            self.pcap_dir, '{}_*.pcap.gz'.format(self.data_type)
        )
        for i, file_path in enumerate(sorted(iglob(glob_pattern))):
            self.api.send_file(self.data_type, file_path, ts,
                               suffix='{:04}'.format(i))
            remove(file_path)

    def execute(self, now=None):
        if not self.check_capture():
            self.start_capture()
        self.compress_pcaps()
        self.push_files(now)
