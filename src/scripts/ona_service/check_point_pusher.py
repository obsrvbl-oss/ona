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
from __future__ import print_function, division, unicode_literals

# python builtins
import logging
import shlex

from collections import defaultdict
from csv import DictWriter
from datetime import datetime, timedelta
from gzip import open as gz_open
from os import environ
from os.path import join

# local
from log_watcher import LogNode
from pusher import Pusher
from utils import create_dirs, timestamp, utcnow

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

ENV_CHECK_POINT_DIR = 'OBSRVBL_CHECK_POINT_LOGDIR'
DEFAULT_CHECK_POINT_DIR = './logs'

ENV_CHECK_POINT_PATH = 'OBSRVBL_CHECK_POINT_PATH'
DEFAULT_CHECK_PATH = '/var/log/check-point-fw.log'

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
POLL_SECONDS = 30


class CheckPointLogNode(LogNode):
    START_STRING = '[Fields@1.3.6.1.4.1.2620 '
    SESSION_FIELDS = (
        'src',
        'dst',
        's_port',
        'service',
        'proto',
        'received_bytes',
        'sent_bytes',
    )

    def __init__(self, *args, **kwargs):
        self.parsed_data = defaultdict(list)
        self.entry = []
        kwargs.setdefault('encoding', 'latin_1')
        super(CheckPointLogNode, self).__init__(*args, **kwargs)

    def _get_dt(self, dt_str):
        # Example: 2016-06-02T15:09:05--5:00
        dt = datetime.strptime(dt_str[:19], '%Y-%m-%dT%H:%M:%S')
        off_sign = 1 if dt_str[19] == '+' else -1
        off_str = dt_str[20:].replace('-', '0').split(':')
        off_hours, off_minutes = int(off_str[0]), int(off_str[1])
        off_delta = timedelta(hours=off_hours, minutes=off_minutes)

        return dt - (off_sign * off_delta)

    def flush_data(self, data, now, compress=True):
        # Loops through the collected lines and looks for ones we know
        # how to parse.
        # Example: "Jun 2 21:22:18 10.64.99.199 2016-06-02T21:19:00--5:00
        # 10.64.99.199 CP-GW - Log [Fields@1.3.6.1.4.1.2620 ...]"
        for line in data:
            # Skip lines we can't interpret
            try:
                i = line.index(self.START_STRING)
                j = line.rindex(']')
                fields = [x.split('=') for x in shlex.split(line[i:j])]
            except ValueError:
                continue
            else:
                D_item = {x[0]: x[1] for x in fields if len(x) == 2}

            # Require all fields to be present
            if any(x not in D_item for x in self.SESSION_FIELDS):
                continue

            # Store the line's data at the associated 10 minute segments
            try:
                dt = self._get_dt(line.split()[4])
            except ValueError:
                continue
            else:
                D_item['timestamp'] = timestamp(dt)
                segment = dt.replace(
                    minute=(dt.minute // 10) * 10, second=0, microsecond=0
                )
                self.parsed_data[segment].append(D_item)


class CheckPointPusher(Pusher):
    """
    Extracts flow data from Check Point the firewall log, bundles it into
    10 minute segments, and sends it to Observable Networks.
    """

    def __init__(self, *args, **kwargs):
        input_dir = environ.get(ENV_CHECK_POINT_DIR, DEFAULT_CHECK_POINT_DIR)
        for key, default in (
            ('file_fmt', '%Y%m%d%H%M%S'),
            ('prefix_len', 14),
            ('data_type', 'csv'),
            ('input_dir', input_dir),
            ('poll_seconds', POLL_SECONDS),
        ):
            kwargs.setdefault(key, default)

        self.tar_mode = 'w'
        super(CheckPointPusher, self).__init__(*args, **kwargs)

        self.log_node = CheckPointLogNode(
            log_type='checkpoint',
            api=self.api,
            log_path=environ.get(ENV_CHECK_POINT_PATH, DEFAULT_CHECK_PATH)
        )

    def _format_item(self, item):
        return {
            'srcaddr': item['src'],
            'dstaddr': item['dst'],
            'srcport': item['s_port'],
            'dstport': item['service'],
            'protocol': item['proto'],
            'bytes_in': item['received_bytes'],
            'bytes_out': item['sent_bytes'],
            'start': item['timestamp'],
            'end': item['timestamp'],
        }

    def _check_point_to_csv(self, send_segment, now):
        # Writes files to the "input" directory so the pusher will find them,
        # archive them, and send them out.

        # The input directory may not have been created yet
        create_dirs(self.input_dir)

        segment_data = self.log_node.parsed_data.pop(send_segment, [])
        if not segment_data:
            return

        file_name = '{}_{}.csv.gz'.format(
            send_segment.strftime(self.file_fmt), now.strftime(self.file_fmt)
        )
        file_path = join(self.input_dir, file_name)
        with gz_open(file_path, 'wt') as outfile:
            writer = DictWriter(outfile, CSV_HEADER)
            writer.writeheader()
            writer.writerows(self._format_item(x) for x in segment_data)

    def execute(self, now=None):
        # Retrieve entries from the log file
        now = now or utcnow()
        self.log_node.check_data(now)

        # We will send data from the previous 10 minute segment
        now_segment = now.replace(
            minute=(now.minute // 10) * 10, second=0, microsecond=0
        )
        send_segment = now_segment - timedelta(minutes=10)

        # Remove data that came in too late to do anything about
        all_segments = sorted(self.log_node.parsed_data.iterkeys())
        for segment in all_segments:
            if segment < send_segment:
                del self.log_node.parsed_data[segment]

        self._check_point_to_csv(send_segment, now)
        super(CheckPointPusher, self).execute(now=now)


if __name__ == '__main__':
    pusher = CheckPointPusher()
    pusher.run()
