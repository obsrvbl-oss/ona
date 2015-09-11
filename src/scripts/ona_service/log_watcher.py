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
from __future__ import print_function, unicode_literals

# python builtins
import io
import logging

from datetime import datetime, timedelta
from glob import glob
from gzip import GzipFile
from json import dumps
from os import fstat, fsync, stat
from os.path import basename, exists, join, splitext
from subprocess import CalledProcessError, check_output, Popen, PIPE
from tempfile import NamedTemporaryFile

# local
from service import Service
from utils import CommandOutputFollower, utcnow, utcoffset, get_ip

# third-party (OS-provided)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

DATA_TYPE = 'logs'
POLL_SECONDS = 10
SEND_DELTA = timedelta(seconds=60)  # want at least a minute between dumps


class WatchNode(object):
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

    def _write_compressed(self, fileobj):
        with GzipFile(fileobj=fileobj, mode='w') as gz_f:
            gz_f.writelines(self.data)

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
        with NamedTemporaryFile() as f:
            if compress:
                self._write_compressed(f)
            else:
                f.writelines(self.data)
            f.flush()
            fsync(f.fileno())
            data = {
                'path': self.api.send_file(DATA_TYPE, f.name, now,
                                           suffix=self.log_type),
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
    def __init__(self, log_type, api, log_path):
        """
        Arguments:
            log_path: location of the log file
            log_type: name to give the log
            api: api for interacting with the proxy
        """
        self.log_path = log_path
        self.log_file = None
        self.log_file_inode = None
        self._set_fd(seek_to_end=True)
        super(LogNode, self).__init__(log_type, api)

    def _set_fd(self, seek_to_end=False):
        try:
            self.log_file = io.open(self.log_path, mode='r')
        except IOError as err:
            logging.error('Could not open %s: %s', self.log_path, err)
            return

        # Get the inode for the open file
        self.log_file_inode = fstat(self.log_file.fileno()).st_ino

        # Read the the end of the last line of the file
        if seek_to_end:
            data = self.log_file.readlines()
            msg = 'Scraping from %s - skipped %s lines'
            logging.info(msg, self.log_path, len(data))

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


class StatNode(WatchNode):
    """
    Unlike LogNode, this reads system stats for logging.
    """
    def __init__(self, log_type, api):
        """
        Arguments:
            log_type: name to give the log
            api: api for interacting with the proxy
        """
        super(StatNode, self).__init__(log_type, api)
        # maintain stats
        self.last_cpu_times = None
        # warm the data up
        self._gather()

    def _cpu_times_percent(self, percpu=False):
        """This attempts to emulate cpu_times_percent._asdict() in later
        versions of psutil."""
        new_cpu_times = psutil.cpu_times(percpu=percpu)
        if not self.last_cpu_times:
            self.last_cpu_times = new_cpu_times
            return {}
        # compute the deltas between old times and new times
        percent_times = []
        for new_times, old_times in zip(new_cpu_times, self.last_cpu_times):
            new_dict = new_times._asdict()
            old_dict = old_times._asdict()
            delta_dict = {k: new_dict[k] - old_dict[k] for k in new_dict}
            total_delta = sum(delta_dict.values())
            if total_delta == 0:
                # the cpu must be broken because it can't just stop.
                return {}
            # convert deltas to percentages
            percent_times.append(
                {k: 100.0 * delta_dict[k] / total_delta for k in delta_dict}
            )
        # update the tracking object
        self.last_cpu_times = new_cpu_times
        return percent_times

    def _virtual_memory(self):
        """Emulate the .virtual_memory() call in later psutil."""
        return dict(psutil.phymem_usage()._asdict())

    def _disk_usage(self, all=False):
        du = []
        for part in psutil.disk_partitions(all=all):
            du.append(
                dict(
                    path=part.mountpoint,
                    **psutil.disk_usage(part.mountpoint)._asdict()
                )
            )
        return du

    def _net_io_counters(self, pernic=False):
        nic_stats = []
        nic_counters = psutil.network_io_counters(pernic=pernic)
        for nic, counters in nic_counters.iteritems():
            stats = {'nic': nic}
            # psutil 0.4.1 does not capture drops/errors/etc. grab those
            ifconfig = Popen(['ifconfig', nic], stdout=PIPE, stderr=PIPE)
            out, __ = ifconfig.communicate()
            for line in out.splitlines():
                line = line.strip()
                # we only care about RX rates for now
                if not line.startswith('RX packets'):
                    continue
                # now we have the RX packets line
                parts = line.split()
                for part in parts[2:]:  # skip "RX" and "packets"
                    try:
                        name, value = part.split(':')
                        value = int(value)
                    except ValueError:
                        continue
                    stats[name] = value
            stats.update(counters._asdict())
            nic_stats.append(stats)
        return nic_stats

    def _gather(self):
        if not HAS_PSUTIL:
            return {}
        start = datetime.utcnow()
        stats = {}

        # cpu utilization (per cpu)
        stats['cpu_times_percent'] = self._cpu_times_percent(percpu=True)

        # memory utilization
        stats['virtual_memory'] = self._virtual_memory()

        # disk utilization
        stats['disk_usage'] = self._disk_usage(all=True)

        # networks stats from all interface (rx/tx/drops/errors/etc)
        stats['net_io_counters'] = self._net_io_counters(pernic=True)

        # some book-keeping
        end = datetime.utcnow()
        stats['starttime'] = start.isoformat()
        stats['runtime'] = str(end - start)
        return stats

    def check_data(self, now=None):
        # no handler -> nothing we can do
        if not HAS_PSUTIL:
            return
        # we only want to gather data once a minute
        now = now or utcnow()
        if (now - self.last_send) >= SEND_DELTA:
            logging.info('gathering stats')
            # get stats, store in data
            data = [dumps(self._gather(), sort_keys=True)]
            self.flush_data(data, now)


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
        super(SystemdJournalNode, self).__init__(log_type, api)

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
        super(LogWatcher, self).__init__(*args, **kwargs)
        self.log_nodes = []

        # Sensor stats
        if kwargs.get('watch_stats', False):
            self.log_nodes.append(
                StatNode(log_type='stats_log', api=self.api)
            )

        # File-based logs
        for name, path in self.logs.iteritems():
            node = LogNode(log_type=name, api=self.api, log_path=path)
            self.log_nodes.append(node)

        # systemd journals
        for name, args in self.journals.iteritems():
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
        watch_stats=True
    )
    try:
        watcher.run()
    finally:
        watcher.clean_all()
