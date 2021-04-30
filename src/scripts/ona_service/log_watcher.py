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

from datetime import timedelta
from glob import glob
from gzip import compress as gz_compress
from os import fstat, fsync, stat
from os.path import basename, exists, join, splitext
from subprocess import CalledProcessError, check_output
from tempfile import NamedTemporaryFile

# local
from ona_service.service import Service
from ona_service.utils import CommandOutputFollower, utcnow, utcoffset, get_ip

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

DATA_TYPE = 'logs'
POLL_SECONDS = 10
SEND_DELTA = timedelta(seconds=60)  # want at least a minute between dumps


class WatchNode:
    def __init__(self, log_type, api, send_delta=SEND_DELTA):
        """
        Arguments:
            log_type: name to give the log
            api: api for interacting with the proxy
        """
        self.log_type = log_type
        self.api = api
        self.checkpoint()
        self.send_delta = send_delta

    def checkpoint(self, now=None):
        self.data = []
        self.last_send = now or utcnow()

    def cleanup(self):
        """
        Closed file descriptors, pipes, sockets, and whatever else might be
        open.
        """

    def flush_data(self, data, now, compress=False):
        # Collect data until it's time to send it out
        self.data.extend(data)
        if (not self.data) or (now - self.last_send < self.send_delta):
            return

        logging.info('Sending data for processing at {}'.format(now))
        with NamedTemporaryFile('w+b') as f:
            if compress:
                f.writelines(gz_compress(line) for line in self.data)
            else:
                f.writelines(self.data)
            f.flush()
            fsync(f.fileno())
            remote_path = self.api.send_file(
                DATA_TYPE, f.name, now, suffix=self.log_type
            )

        if remote_path is not None:
            data = {
                'path': remote_path,
                'log_type': self.log_type,
                'utcoffset': utcoffset(),
                'ip': get_ip(),
            }
            self.api.send_signal(DATA_TYPE, data)

        self.checkpoint(now)

    def check_data(self, now=None):
        raise NotImplementedError()


class LogNode(WatchNode):
    """
    Object to handle reading of a log file.
    """
    def __init__(self, log_type, api, log_path, **kwargs):
        """
        Arguments:
            log_path: location of the log file
            log_type: name to give the log
            api: api for interacting with the proxy
        """
        self.encoding = kwargs.pop('encoding', 'utf-8')
        self.errors = kwargs.pop('errors', 'ignore')
        self.log_path = log_path
        self.log_file = None
        self.log_file_inode = None
        self._set_fd(seek_to_end=True)
        super().__init__(log_type, api)

    def _set_fd(self, seek_to_end=False):
        try:
            self.log_file = open(
                self.log_path,
                mode='rt',
                encoding=self.encoding,
                errors=self.errors,
            )
        except OSError as err:
            logging.error('Could not open %s: %s', self.log_path, err)
            return

        # Get the inode for the open file
        self.log_file_inode = fstat(self.log_file.fileno()).st_ino

        # Read the the end of the last line of the file
        if seek_to_end:
            line_count = sum(1 for line in self.log_file)
            msg = 'Scraping from %s - skipped %s lines'
            logging.info(msg, self.log_path, line_count)

    def cleanup(self):
        try:
            self.log_file.close()
        except AttributeError:
            pass
        self.log_file = None
        self.log_file_inode = None

    def check_data(self, now=None):
        # Log was reset - read from the beginning
        if self.log_file is None:
            self._set_fd(seek_to_end=False)

        # Still could not set the file descriptor - try again next time
        if self.log_file is None:
            return

        # Retrieve line-buffered data from the log
        data = self.log_file.readlines()
        data = [x.encode(self.encoding, errors=self.errors) for x in data]
        self.flush_data(data, now, compress=True)

        # Check to see if the inode associated with the log path has changed.
        # If it has, reload.
        try:
            inode = stat(self.log_path).st_ino
        except OSError:
            self.cleanup()
            return

        if inode != self.log_file_inode:
            self.cleanup()


class SystemdJournalNode(WatchNode):
    def __init__(self, log_type, api, journalctl_args):
        """
        Arguments:
            log_type: name to give the log
            api: api for interacting with the proxy
            journalctl_args: a sequence of arguments to pass to journalctl,
              for example: ['--unit=ssh.service', 'SYSLOG_FACILITY=10']
        """
        self.unit_name = log_type
        super().__init__(log_type, api)

        self.command_args = ['journalctl', '-f', '--lines=1'] + journalctl_args
        self._start_follower()

    def cleanup(self):
        self.follower.cleanup()

    def _start_follower(self):
        self.follower = CommandOutputFollower(self.command_args)
        self.follower.start_process()

    def check_data(self, now):
        if not self.follower.check_process():
            self.cleanup()
            self._start_follower()

        data = []
        while True:
            line = self.follower.read_line(0.1)
            if line is None:
                break
            data.append(line)

        self.flush_data(data, now, compress=True)


class LogWatcher(Service):
    """
    Watches a set of log files for changes and periodically pushes them to
    S3.
    """

    def __init__(self, *args, **kwargs):
        self.logs = kwargs.pop('logs', {})
        self.journals = kwargs.pop('journals', {})
        kwargs.update({
            'poll_seconds': POLL_SECONDS,
        })
        super().__init__(*args, **kwargs)
        self.log_nodes = []

        # File-based logs
        for name, path in self.logs.items():
            node = LogNode(log_type=name, api=self.api, log_path=path)
            self.log_nodes.append(node)

        # systemd journals
        for name, args in self.journals.items():
            node = SystemdJournalNode(
                log_type=name, api=self.api, journalctl_args=args
            )
            self.log_nodes.append(node)

    def clean_all(self):
        for node in self.log_nodes:
            node.cleanup()

    def execute(self, now=None):
        for node in self.log_nodes:
            node.check_data(now)


def directory_logs(logdir, prefix, extension='.log'):
    """
    Finds the log paths in `logdir` that start with `prefix` and end with
    `extension` (include the dot). Returns a dictionary.
    """
    ret = {}
    pattern = join(logdir, '{}*{}'.format(prefix, extension))
    for file_path in glob(pattern):
        file_name, __ = splitext(basename(file_path))
        ret[file_name] = file_path

    return ret


def check_auth_journal():
    """
    Queries the systemd journal for authpriv (facility 10) entries. If there
    are any present, return True; otherwise return False.
    """
    try:
        check_output(['journalctl', 'SYSLOG_FACILITY=10'])
    except (CalledProcessError, OSError):
        return False
    return True


if __name__ == '__main__':
    logs = {}
    journals = {}

    # Look for the authpriv log
    if exists('/var/log/auth.log'):
        logs.update({'auth.log': '/var/log/auth.log'})
    elif check_auth_journal():
        journals.update({'auth.log': ['SYSLOG_FACILITY=10']})

    # Monitor the Observable ONA service logs
    logs.update(directory_logs('/opt/obsrvbl-ona/logs/ona_service', 'ona-'))

    watcher = LogWatcher(
        logs=logs,
        journals=journals,
    )
    try:
        watcher.run()
    finally:
        watcher.clean_all()
