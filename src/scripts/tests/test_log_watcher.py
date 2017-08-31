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

import gzip

from collections import namedtuple
from datetime import datetime, timedelta
from glob import iglob
from json import loads
from os import rename
from os.path import join
from shutil import rmtree
from tempfile import mkdtemp, NamedTemporaryFile
from unittest import TestCase

from mock import MagicMock, Mock, patch

from ona_service.log_watcher import (
    check_auth_journal,
    directory_logs,
    LogWatcher,
    LogNode,
    StatNode,
    SystemdJournalNode,
    WatchNode,
)
from ona_service.utils import utcnow


class MSUtilBase(object):
    """
    Not Microsoft. Mock pS util.
    """
    cpu_time_calls = 0

    @staticmethod
    def cpu_times(percpu=False):
        t = namedtuple('cputimes', 'user,nice,system,idle')
        if MSUtilBase.cpu_time_calls == 1:
            ret = t(50, 0, 500, 5000)
        else:
            ret = t(55, 0, 600, 6000)
        MSUtilBase.cpu_time_calls += 1
        return [ret]

    @staticmethod
    def disk_partitions(all=True):
        t = namedtuple('partition', 'device,mountpoint,fstype')
        return [t('/dev/sda1', '/', 'ext4')]

    @staticmethod
    def disk_usage(path):
        t = namedtuple('usage', 'total,used,free,percent')
        return t(150, 40, 110, 88.3)


class MSUtilOld(MSUtilBase):
    @staticmethod
    def phymem_usage():
        t = namedtuple('usage', 'total,used,free,percent')
        return t(20, 18, 4, 80.0)

    @staticmethod
    def network_io_counters(pernic=True):
        t = namedtuple('iostat', 'B_sent,B_recv,p_sent,p_recv')
        return {'lo': t(30, 30, 18, 18)}


class MSUtilNew(MSUtilBase):
    @staticmethod
    def virtual_memory():
        t = namedtuple('usage', 'total,used,free,percent')
        return t(21, 19, 5, 81.0)

    @staticmethod
    def net_io_counters(pernic=True):
        t = namedtuple('iostat', 'B_sent,B_recv,p_sent,p_recv')
        return {'lo': t(31, 31, 19, 19)}


class StatNodeTest(TestCase):
    def setUp(self):
        logs = {'test-log': '/tmp/test.log'}
        self.watcher = LogWatcher(logs=logs, watch_stats=True)
        self.maxDiff = None

    @patch('ona_service.log_watcher.HAS_PSUTIL', False)
    def test_statnode_nopsutil(self):
        # No psutil -> just don't exception out
        node = StatNode(log_type='stats_log', api=self.watcher.api)
        node.check_data()
        stats = node._gather()
        self.assertEqual(stats, {})

    @patch('ona_service.log_watcher.psutil', MSUtilOld, create=True)
    @patch('ona_service.log_watcher.Popen', autospec=True)
    def test_statnode_nic_old(self, mock_Popen):
        # predictable Popen().communicate
        out = (
            'lo\tLink encap:Ethernet  HWaddr ff:ff:ff:ff:ff:3f\n'
            'inet6 addr: ffff::fff:ffff:ffff:fff/64 Scope:Link\n'
            'UP BROADCAST RUNNING PROMISC MULTICAST\n'
            'MTU:1500  Metric:1\n'
            'RX packets:19738210 errors:f dropped:8 overruns:1 frame 5\n'
            'RX bytes:2131412\n'
        )
        mock_Popen(['ifconfig', 'lo']).communicate.return_value = (out, '')

        node = StatNode(log_type='stats_log', api=self.watcher.api)
        stats = node._net_io_counters()
        expected_stats = [
            {'nic': 'lo', 'B_recv': 30, 'B_sent': 30, 'p_recv': 18,
             'p_sent': 18, 'dropped': 8, 'overruns': 1}
        ]
        self.assertEqual(stats, expected_stats)

    @patch('ona_service.log_watcher.psutil', MSUtilNew, create=True)
    @patch('ona_service.log_watcher.Popen', autospec=True)
    def test_statnode_nic_new(self, mock_Popen):
        # predictable Popen().communicate
        out = (
            'lo\tLink encap:Ethernet  HWaddr ff:ff:ff:ff:ff:3f\n'
            'inet6 addr: ffff::fff:ffff:ffff:fff/64 Scope:Link\n'
            'UP BROADCAST RUNNING PROMISC MULTICAST\n'
            'MTU:1500  Metric:1\n'
            'RX packets:19738210 errors:f dropped:8 overruns:1 frame 5\n'
            'RX bytes:2131412\n'
        )
        mock_Popen(['ifconfig', 'lo']).communicate.return_value = (out, '')

        node = StatNode(log_type='stats_log', api=self.watcher.api)
        stats = node._net_io_counters()
        expected_stats = [
            {'nic': 'lo', 'B_recv': 31, 'B_sent': 31, 'p_recv': 19,
             'p_sent': 19, 'dropped': 8, 'overruns': 1}
        ]
        self.assertEqual(stats, expected_stats)

    @patch('ona_service.log_watcher.psutil', MSUtilOld, create=True)
    def test_statnode_virtual_memory_old(self):
        node = StatNode(log_type='stats_log', api=self.watcher.api)
        actual = node._virtual_memory()
        expected = {'free': 4, 'percent': 80.0, 'total': 20, 'used': 18}
        self.assertEqual(actual, expected)

    @patch('ona_service.log_watcher.psutil', MSUtilNew, create=True)
    def test_statnode_virtual_memory_new(self):
        node = StatNode(log_type='stats_log', api=self.watcher.api)
        actual = node._virtual_memory()
        expected = {'free': 5, 'percent': 81.0, 'total': 21, 'used': 19}
        self.assertEqual(actual, expected)

    @patch('ona_service.log_watcher.HAS_PSUTIL', True)
    @patch('ona_service.log_watcher.Popen', autospec=True)
    @patch('ona_service.log_watcher.psutil', MSUtilOld, create=True)
    @patch('ona_service.api.requests', autospec=True)
    @patch('ona_service.log_watcher.datetime', autospec=True)
    def test_statnode(self, mock_dt, mock_requests, mock_Popen):
        now = datetime.utcnow()
        mock_dt.utcnow.return_value = now
        # predictable Popen().communicate
        mock_Popen(['ifconfig', 'lo']).communicate.return_value = ('', '')
        # No psutil -> just don't exception out
        node = StatNode(log_type='stats_log', api=self.watcher.api)
        stats = node._gather()
        expected_stats = {
            'cpu_times_percent': [
                {'idle': 90.49773755656109, 'nice': 0.0,
                 'system': 9.049773755656108, 'user': 0.45248868778280543}
            ],
            'virtual_memory': {
                'free': 4, 'percent': 80.0, 'total': 20, 'used': 18
            },
            'disk_usage': [
                {'total': 150, 'path': '/', 'used': 40,
                 'percent': 88.3, 'free': 110}
            ],
            'net_io_counters': [
                {'nic': 'lo', 'B_recv': 30, 'B_sent': 30,
                 'p_recv': 18, 'p_sent': 18}
            ],
            'starttime': now.isoformat(),
            'runtime': '0:00:00',
        }
        self.assertEqual(stats, expected_stats)

        def fetch_request(*args, **kwargs):
            data = kwargs['data'].read()
            data_dict = loads(data)
            # verify the data we're sending matches our expectation
            self.assertEqual(expected_stats, data_dict)
            return Mock()
        mock_requests.request.side_effect = fetch_request

        # now check the stuff we'll send (trigger the 1 minute interval)
        with patch('ona_service.log_watcher.utcnow') as mock_now:
            mock_now.side_effect = lambda: now + timedelta(seconds=61)
            node.check_data()
        # assertion is in fetch_request callback


class LogNodeTestCase(TestCase):
    def setUp(self):
        self.tmpdir = mkdtemp()
        self.dummy_file = join(self.tmpdir, 'dummy')
        self.node = LogNode('one', None, self.dummy_file)
        self.now = datetime.utcnow()

    def tearDown(self):
        rmtree(self.tmpdir)

    def test_check_data_none(self):
        # file doesn't exist yet
        self.node.check_data(self.now)
        self.assertIsNone(self.node.log_file)
        self.assertIsNone(self.node.log_file_inode)

    def test_check_data_created(self):
        # create the file and write a line
        with open(self.dummy_file, 'w') as f:
            print('hello', file=f)  # should be saved, wasn't there at init
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, ['hello\n'])
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

        with open(self.dummy_file, 'a') as f:
            print('foo', file=f)  # will be saved, new in this run
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, ['hello\n', 'foo\n'])
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

    def test_check_data_rolled(self):
        # create the file and write a line
        with open(self.dummy_file, 'w') as f:
            print('hello', file=f)
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, ['hello\n'])
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

        with open(self.dummy_file, 'a') as f:
            print('foo', file=f)  # will be saved, new in this run
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, ['hello\n', 'foo\n'])
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

        # write one last line to the old file
        with open(self.dummy_file, 'a') as f:
            print('bar', file=f)
        # rename the file, should persist inode
        rename(self.dummy_file, '{}.{}'.format(self.dummy_file, 1))

        # now create a new file
        with open(self.dummy_file, 'w') as f:
            print('bye', file=f)  # should be saved, new file
        # first call should notice that the file has changed, grab the
        # remainder of the last file
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, ['hello\n', 'foo\n', 'bar\n'])
        # second call will grab the new file
        self.node.check_data(self.now)
        self.assertEqual(
            self.node.data,
            ['hello\n', 'foo\n', 'bar\n', 'bye\n']
        )
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

        # this time, we'll rename but not create
        with open(self.dummy_file, 'a') as f:
            print('hi', file=f)  # should be saved, new file
        # rename the file, should persist inode
        rename(self.dummy_file, '{}.{}'.format(self.dummy_file, 1))
        self.node.check_data(self.now)
        self.assertEqual(
            self.node.data,
            ['hello\n', 'foo\n', 'bar\n', 'bye\n', 'hi\n']
        )
        # because the file is rolling, no known next file exists
        self.assertIsNone(self.node.log_file)
        self.assertIsNone(self.node.log_file_inode)

    def test__set_fd(self):
        with open(self.dummy_file, 'w') as f:
            f.write('hello world')

        self.node._set_fd()
        inode1 = self.node.log_file_inode
        with open(self.dummy_file, 'r') as f:
            contents = f.read()
        self.assertEqual(self.node.log_file.read(), contents)
        self.node._set_fd(seek_to_end=True)
        inode2 = self.node.log_file_inode
        self.assertEqual(self.node.log_file.read(), '')
        self.assertEqual(inode1, inode2)


class SystemdJournalNodeTestCase(TestCase):
    @patch('ona_service.log_watcher.CommandOutputFollower', autospec=True)
    def test_check_data(self, mock_CommandOutputFollower):
        mock_follower = MagicMock()
        mock_CommandOutputFollower.return_value = mock_follower

        node = SystemdJournalNode(
            log_type='auth.log',
            api=None,
            journalctl_args=['SYSLOG_FACILITY=10']
        )
        self.now = datetime.utcnow()

        return_values = ['0\n', '1\n', '2\n', None]

        def side_effect(*args, **kwargs):
            return return_values.pop(0)

        mock_follower.check_process.return_value = False
        mock_follower.read_line.side_effect = side_effect

        node.check_data(self.now)
        self.assertEqual(mock_follower.start_process.call_count, 2)

        self.assertEqual(node.data, ['0\n', '1\n', '2\n'])


class LogWatcherMainTestCase(TestCase):
    @patch('ona_service.log_watcher.SystemdJournalNode', autospec=True)
    @patch('ona_service.log_watcher.StatNode', autospec=True)
    @patch('ona_service.log_watcher.LogNode', autospec=True)
    def test_LogWatcherInit(
        self,
        mock_LogNode,
        mock_StatNode,
        mock_SystemdJournalNode
    ):
        watcher = LogWatcher(
            logs={'log_name': 'log_path'},
            journals={'journal_name': ['SOME_FIELD=SOME_VALUE']},
            watch_stats=True
        )
        self.assertEqual(len(watcher.log_nodes), 3)

        mock_StatNode.assert_called_once_with(
            log_type='stats_log',
            api=watcher.api,
        )
        mock_LogNode.assert_called_once_with(
            log_type='log_name',
            api=watcher.api,
            log_path='log_path'
        )
        mock_SystemdJournalNode.assert_called_once_with(
            log_type='journal_name',
            api=watcher.api,
            journalctl_args=['SOME_FIELD=SOME_VALUE'],
        )

    @patch('ona_service.log_watcher.StatNode', autospec=True)
    @patch('ona_service.log_watcher.LogNode', autospec=True)
    def test_service(self, mock_lognode, mock_statnode):
        watcher = LogWatcher(
            logs={'auth.log': '/tmp', 'two': '/tmp/two'},
            watch_stats=True
        )
        watcher.execute('now')
        lognode = mock_lognode.return_value
        self.assertEqual(lognode.check_data.call_count, 2)
        lognode.check_data.assert_called_with('now')
        statnode = mock_statnode.return_value
        statnode.check_data.assert_called_with('now')

    @patch('ona_service.log_watcher.glob', autospec=True)
    def test_directory_logs(self, mock_glob):
        mock_glob.return_value = [
            '/opt/obsrvbl-ona/logs/ona_service/ona-one.log',
            '/opt/obsrvbl-ona/logs/ona_service/ona-two.log',
        ]

        actual = directory_logs('/opt/obsrvbl-ona/logs/ona_service', 'ona-')
        expected = {
            'ona-one': '/opt/obsrvbl-ona/logs/ona_service/ona-one.log',
            'ona-two': '/opt/obsrvbl-ona/logs/ona_service/ona-two.log',
        }
        self.assertEqual(actual, expected)

        mock_glob.assert_called_once_with(
            '/opt/obsrvbl-ona/logs/ona_service/ona-*.log'
        )

    @patch('ona_service.log_watcher.check_output', autospec=True)
    def test_check_auth_journal(self, mock_check_output):
        # Success
        mock_check_output.return_value = 0
        self.assertTrue(check_auth_journal())

        # Failure
        mock_check_output.side_effect = OSError
        self.assertFalse(check_auth_journal())


class WatchNodeTestCase(TestCase):
    def setUp(self):
        self.mock_api = MagicMock()
        self.now = utcnow()
        self.later = self.now + timedelta(seconds=1)
        self.test_data = [b'line_1\n', b'line_2\n']

        self.inst = WatchNode('test_type', self.mock_api, timedelta(seconds=1))
        self.inst.last_send = self.now

        # Creates a temporary file in a known location
        self.tmpdir = mkdtemp()

        def fixed_temp_file(*args, **kwargs):
            return NamedTemporaryFile(delete=False, dir=self.tmpdir)

        self.fixed_temp_file = fixed_temp_file

    def tearDown(self):
        rmtree(self.tmpdir)

    def test_flush_data_compressed(self):
        patch_src = 'ona_service.log_watcher.NamedTemporaryFile'
        with patch(patch_src, self.fixed_temp_file):
            self.inst.flush_data(self.test_data, self.later, compress=True)

        # Gzip-read of the file should give back the input data
        for file_path in iglob(join(self.tmpdir, '*')):
            with gzip.open(file_path, 'rb') as infile:
                self.assertEqual(infile.read(), ''.join(self.test_data))

    def test_flush_data_uncompressed(self):
        patch_src = 'ona_service.log_watcher.NamedTemporaryFile'
        with patch(patch_src, self.fixed_temp_file):
            self.inst.flush_data(self.test_data, self.later)

        # Direct read of the file should give back the input data
        for file_path in iglob(join(self.tmpdir, '*')):
            with open(file_path, 'r') as infile:
                self.assertEqual(infile.read(), ''.join(self.test_data))

    def test_flush_data_calls(self):
        # No data -> no calls
        self.inst.flush_data([], self.later)
        self.assertEqual(self.mock_api.send_signal.call_count, 0)

        # Not enough time has passed -> no calls
        self.inst.flush_data(self.test_data, self.now)
        self.assertEqual(self.mock_api.send_signal.call_count, 0)

        # Data is present, enough time has passed -> one call
        self.inst.flush_data(self.test_data, self.later)
        self.assertEqual(self.mock_api.send_signal.call_count, 1)
