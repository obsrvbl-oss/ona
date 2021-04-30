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
import json
import socket

from calendar import timegm
from datetime import datetime, timezone
from ipaddress import ip_address, IPv4Interface as ip_interface
from os import devnull, makedirs
from queue import Queue, Empty
from subprocess import PIPE, Popen
from threading import Event, Thread
from time import mktime, sleep


utc = timezone.utc


def utcnow():
    """
    Get the current UTC time, but strip microseconds because we don't want
    them.
    """
    return datetime.utcnow().replace(microsecond=0)


def utcoffset(now=None):
    """
    Find the seconds offset from UTC for this system's clock.
    """
    now = now or utcnow()
    ts = mktime(now.timetuple())
    # fromtimestamp takes the time and sets it to system time
    # utcfromtimestam gives the time in UTC
    delta = datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)
    return int(delta.total_seconds())


def get_ip():
    """Returns one of the IP addresses of the associated hosts"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(('1.1.1.1', 9000))  # IP and port are arbitrary
    ip = sock.getsockname()[0]  # returns (hostaddr, port)
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()
    return ip


def create_dirs(path):
    """Create the given path on the filesystem idempotently."""
    makedirs(path, exist_ok=True)


# CommandOutputFollower is inspired by J.F. Sebastian's method for non-blocking
# reads from subprocess calls at http://stackoverflow.com/a/4896288/353839 .
class CommandOutputFollower:
    """
    Reads the output of commands that produce output forever (e.g. tail -f)
    without blocking.
    """

    def __init__(self, command_args):
        """
        `command_args` is a sequence of strings to pass to the Popen
        constructor's `args` argument.
        """
        self.command_args = command_args
        self.process = None
        self.stdout_file = None
        self.stderr_file = None
        self.stop_event = Event()

    def __enter__(self):
        self.start_process()
        return self

    def __exit__(self, type_, value, traceback):
        self.cleanup()

    def check_process(self):
        """
        If the process is running, return True. Otherwise return False.
        """
        # Not started yet
        if self.process is None:
            return False

        # Terminated early
        if self.process.poll() is not None:
            return False

        # Still running
        return True

    def cleanup(self):
        """
        Close the file objects like a responsible citizen.
        """
        try:
            self.process.terminate()
        except (AttributeError, OSError):
            pass

        self.stop()
        sleep(0.1)

        try:
            self.stdout_file.close()
        except AttributeError:
            pass

        try:
            self.stderr_file.close()
        except AttributeError:
            pass

    def enqueue_line(self):
        """
        Read lines from the stdout file object and put them on the queue.
        """
        for line in iter(self.stdout_file.readline, b''):
            if self.stop_event.is_set():
                break
            self.queue.put(line)

        self.cleanup()

    def read_line(self, timeout=None):
        """
        If there was a line available, retrieve it from the queue and return
        it. Otherwise, return None.
        """
        if timeout is None:
            get_kwargs = {'block': False}
        else:
            get_kwargs = {'timeout': timeout}
        try:
            return self.queue.get(**get_kwargs)
        except Empty:
            return None

    def start_process(self):
        """
        Start the process and the thread that reads it.
        """
        self.stderr_file = open(devnull, 'wb')
        self.process = Popen(
            self.command_args,
            stdout=PIPE,
            stderr=self.stderr_file,
            bufsize=1,
            close_fds=True
        )
        self.stdout_file = self.process.stdout

        self.queue = Queue()
        self.stop_event.clear()
        self.thread = Thread(target=self.enqueue_line)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.stop_event.set()


def validate_pna_networks(site_value):
    """
    Given a string with CIDR networks separated by whitespace, return
    normalized versions of the ones that use valid notation separated by
    spaces. If there was nothing valid, return an empty string.

    Everything valid:
    Example input: validate_pna_networks('10.0.0.0/8\n192.168.0.0/16')
    Example output: '10.0.0.0/8 192.168.0.0/16'

    One invalid subnet/mask corrected:
    Example input: validate_pna_networks('10.0.0.0/8\n192.168.168.0/16')
    Example output: '10.0.0.0/8 192.168.0.0/16'

    Nothing valid:
    Example input: validate_pna_networks('sudo adduser evilperson')
    Example output: ''
    """
    output_list = []

    try:
        site_items = site_value.split()
    except AttributeError:
        return ''

    for item in site_items:
        try:
            normalized_string = str(ip_interface(item).network)
        except ValueError:
            continue
        output_list.append(normalized_string)

    return ' '.join(output_list)


def timestamp(dt):
    """Convert a date or datetime to a UNIX timestamp (integer)."""
    return timegm(dt.utctimetuple())


class persistent_dict(dict):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self._load()

    def _load(self):
        self.clear()
        try:
            with open(self.filename) as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass

    def _save(self):
        with open(self.filename, 'w') as f:
            return json.dump(self, f)

    def __setitem__(self, key, value):
        res = super().__setitem__(key, value)
        self._save()
        return res


def is_ip_address(x):
    try:
        ip_address(x)
    except ValueError:
        return False

    return True


def exploded_ip(ip, V4_PREFIX=b'\x00' * 12):
    if ':' in ip:
        packed = socket.inet_pton(socket.AF_INET6, ip)
    else:
        packed = V4_PREFIX + socket.inet_pton(socket.AF_INET, ip)

    return packed.hex()
