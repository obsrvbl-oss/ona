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
import gzip
import json
import socket

from calendar import timegm
from datetime import datetime, timedelta, tzinfo
from os import devnull, makedirs
from Queue import Queue, Empty
from socket import error as socket_error, inet_aton, inet_ntoa
from struct import pack, unpack
from subprocess import PIPE, Popen
from tempfile import NamedTemporaryFile
from threading import Event, Thread
from time import mktime, sleep


ZERO_DELTA = timedelta(0)


class UTC(tzinfo):
    """UTC"""
    def utcoffset(self, dt):
        return ZERO_DELTA

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO_DELTA


utc = UTC()


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
    try:
        makedirs(path)
    except OSError:
        pass


# CommandOutputFollower is inspired by J.F. Sebastian's method for non-blocking
# reads from subprocess calls at http://stackoverflow.com/a/4896288/353839 .
class CommandOutputFollower(object):
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
        self.stderr_file = io.open(devnull, 'wb')
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


def normalize_subnet(prefix, mask_length):
    """
    Given a string `prefix` with the first IP address in an IPv4 CIDR block,
    and a string `mask_length` representing the length of the subnet mask for
    that block, return a string with the CIDR representation of the block.
    e.g. normalize_subnet('192.168.0.0', '16') => '192.168.0.0/16'

    Returns None if the IP address or mask length is not valid for IPv4.
    e.g. normalize_subnet('192.168.256.0', '16') => None
    e.g. normalize_subnet('192.168.0.0', '33') => None

    Masks off the host bits of the IP address if they are not 0.
    e.g. normalize_subnet('192.168.100.0', '16') => '192.168.0.0/16'
    """
    # Validate the prefix
    try:
        prefix = unpack(b'!I', inet_aton(prefix))[0]
    except socket_error:
        return None

    # Validate the length
    try:
        mask_length = int(mask_length)
    except ValueError:
        return None

    if not (0 <= mask_length <= 32):
        return None

    # Apply the mask to the prefix
    mask = ((1 << 32) - 1) ^ ((1 << (32 - mask_length)) - 1)
    normal_prefix = inet_ntoa(pack('!I', prefix & mask))

    # Return a properly-formatted string
    return '{}/{}'.format(normal_prefix, mask_length)


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
        item = item.split('/')
        if len(item) != 2:
            continue

        prefix, mask_length = item
        normalized_string = normalize_subnet(prefix, mask_length)
        if normalized_string is not None:
            output_list.append(normalized_string)

    return ' '.join(output_list)


def send_observations(api, obs_type, obs_data, now, suffix=''):
    """
    Upload an observations file to the ON service.
    `api` is an ON API object.
    `obs_type` is a string with the name of the observation resource.
    `obs_data` is an iterable of dicts with observation data.
    `now` is a datetime object.
    `suffix` is a string to be appended to the file name.
    """
    if not obs_data:
        return

    with NamedTemporaryFile() as f:
        for obs in obs_data:
            obs['observation_type'] = obs_type
            obs_json = json.dumps(obs, sort_keys=True).encode('utf-8')
            f.write(obs_json)
            f.write(b'\n')

        f.seek(0)
        path = api.send_file('logs', f.name, now, suffix=suffix)

    if path is not None:
        data = {'path': path, 'log_type': 'observations'}
        api.send_signal('logs', data)


def timestamp(dt):
    """Convert a date or datetime to a UNIX timestamp (integer)."""
    return timegm(dt.utctimetuple())


def gunzip_bytes(gz_bytes, *args, **kwargs):
    with io.BytesIO(gz_bytes) as fd:
        with gzip.GzipFile(fileobj=fd, mode='rb') as gz_fd:
            return gz_fd.read()


def gzip_bytes(raw_bytes, *args, **kwargs):
    with io.BytesIO() as fd:
        with gzip.GzipFile(fileobj=fd, mode='wb') as gz_fd:
            gz_fd.write(raw_bytes)

        return fd.getvalue()


class persistent_dict(dict):
    def __init__(self, filename):
        super(persistent_dict, self).__init__()
        self.filename = filename
        self._load()

    def _load(self):
        self.clear()
        try:
            with open(self.filename, 'r') as f:
                self.update(json.load(f))
        except (IOError, ValueError):
            pass

    def _save(self):
        with open(self.filename, 'w') as f:
            return json.dump(self, f)

    def __setitem__(self, key, value):
        res = super(persistent_dict, self).__setitem__(key, value)
        self._save()
        return res


def is_ip_address(x):
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, x)
        except socket.error:
            pass
        else:
            return True

    return False
