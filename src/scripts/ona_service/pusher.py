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
# python builtins
import logging

from collections import defaultdict
from datetime import datetime, timedelta
from glob import iglob
from os import makedirs, remove
from os.path import basename, getsize, join
from tarfile import open as tar_open
from tempfile import gettempdir


# local
from ona_service.service import Service
from ona_service.utils import utc


FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

MAX_BACKLOG_DELTA = timedelta(days=2)


class Pusher(Service):
    """
    Aggregate data on ten minute intervals and push to the Observable cloud for
    processing.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the pusher object.

        Keyword Arguments:
            data_type: type of data that is being pushed
            file_fmt: `strftime` compat format for file names
            prefix_len: length of file prefix to determine bounds (10 minutes)
            input_dir: path to search for files
        """
        super().__init__(*args, **kwargs)

        self.data_type = kwargs.pop('data_type')

        self.file_fmt = kwargs.pop('file_fmt', None)
        self.prefix_len = kwargs.pop('prefix_len', None)

        self.input_dir = kwargs.pop('input_dir', None)
        self.output_dir = join(gettempdir(), self.data_type)

    def send_heartbeat(self, dt=None):
        """
        Send a signal to the site to tell it we're here.
        """
        dt = dt or datetime.now(utc)
        dt = dt.astimezone(utc) if dt.tzinfo else dt.replace(tzinfo=utc)
        data = {
            'data_type': self.data_type,
            'sensor_hb_time': dt.isoformat(),
        }
        self.api.send_signal(data_type='heartbeat', data=data)

    def send_sensor_data(self, path, dt):
        """
        Sends the sensor data, then signals the site about the data's
        arrival.

        Args:
            path: input path where data to transfer is located
            whence: time that the data represents
        """
        dt = dt.astimezone(utc) if dt.tzinfo else dt.replace(tzinfo=utc)

        output_path = self.api.send_file(self.data_type, path, dt)
        if output_path is None:
            return False

        data = {
            'timestamp': dt.isoformat(),
            'data_type': self.data_type,
            'data_path': output_path,
        }
        return self.api.send_signal(data_type='sensordata', data=data)

    def _get_file_datetime(self, file_path):
        """
        Given a `file_path` that conforms to the date format in self.file_fmt,
        return a datetime object, rounded down to the nearest 10-minute
        boundary.
        Example: If self.file_fmt is '%Y-%m-%d %H:%M%S' and file_path is
        '2015-07-11 16:19:59' we get datetime(2015, 7, 11, 16, 10).
        """
        file_name = basename(file_path)
        prefix = file_name[:self.prefix_len]
        dt = datetime.strptime(prefix, self.file_fmt)
        minute = (dt.minute // 10) * 10
        return dt.replace(minute=minute, second=0, microsecond=0)

    def _create_archives(self, D_archive):
        """
        Given `D_archive`, a dictionary whose keys are datetime objects
        representing 10-minute bins and whose values are lists of files,
        create one archive per completed bin and then delete the files.
        """
        makedirs(self.output_dir, exist_ok=True)

        # Don't touch the most recent 10-minute bin; it may still be active
        file_bins = sorted(D_archive.keys())[:-1]
        for key in file_bins:
            file_list = D_archive[key]

            # Process the files before archiving
            self._process_files(file_list)

            # Create the file archive
            prefix = format(key, self.file_fmt)
            archive_name = '{}.{}'.format(prefix, self.api.ona_name)

            archive_path = join(self.output_dir, archive_name)
            logging.info('Creating archive %s', archive_name)
            self._archive_files(file_list, archive_path)

            # Remove the now-archived files
            for file_path in file_list:
                self._remove_file(file_path)

    def _process_files(self, file_list):
        """
        Child classes may override this method to make some transformation to
        input files before archiving.
        """
        pass

    def _archive_files(self, file_list, archive_path):
        with tar_open(archive_path, mode=self.tar_mode) as tarball:
            for file_path in file_list:
                try:
                    tarball.add(file_path, arcname=basename(file_path))
                except OSError:
                    logging.warning('Could not add %s', file_path)

    def _remove_file(self, file_path):
        try:
            remove(file_path)
        except OSError:
            logging.warning('Could not remove {}.'.format(file_path))

    def _send_archives(self, now):
        """
        Sends everything in the output directory using self.send_sensor_data,
        removing what's been successfully sent.
        """
        for file_path in sorted(iglob(join(self.output_dir, '*'))):
            # Skip any files that don't seem to match our format
            try:
                whence = self._get_file_datetime(file_path)
            except ValueError:
                continue

            # Skip any files that have been truncated (this should be
            # impossible, but you'd be surprised)
            if getsize(file_path) == 0:
                continue

            # remove very old files
            if (now - whence) >= MAX_BACKLOG_DELTA:
                self._remove_file(file_path)
                continue

            # attempt to send the file, removing those that have been
            # successfully transmitted
            if not self.send_sensor_data(file_path, whence):
                logging.warning('Could not send %s', file_path)
                continue

            self._remove_file(file_path)

    def _get_file_bins(self):
        """
        Read through the files in the input directory, aggregating them by file
        name into 10-minute bins. Returns a dict whose keys are datetime
        objects and whose values are lists of file paths.
        """
        D_archive = defaultdict(list)
        for file_path in sorted(iglob(join(self.input_dir, '*'))):
            try:
                key = self._get_file_datetime(file_path)
            except ValueError:
                continue
            D_archive[key].append(file_path)

        return D_archive

    def execute(self, now=None):
        logging.info('Pushing files from %s', self.input_dir)

        # Send a heartbeat to the site
        self.send_heartbeat(now)

        # Aggregate the file paths into 10-minute bins
        D_archive = self._get_file_bins()
        file_count = sum(len(v) for v in D_archive.values())
        logging.info('Found %s files', file_count)

        # Create archives of the input files and then remove the originals
        self._create_archives(D_archive)

        # Send out the archive files we've collected and then remove them
        self._send_archives(now)
