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
import gzip

from datetime import datetime, timedelta
from glob import iglob
from os import rename
from os.path import join
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ona_service.log_watcher import (
    check_auth_journal,
    directory_logs,
    LogWatcher,
    LogNode,
    SystemdJournalNode,
    WatchNode,
)
from ona_service.utils import utcnow


class LogNodeTestCase(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.dummy_file = join(self.temp_dir.name, 'dummy')
        self.node = LogNode('one', None, self.dummy_file)
        self.now = datetime.utcnow()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_check_data_none(self):
        # file doesn't exist yet
        self.node.check_data(self.now)
        self.assertIsNone(self.node.log_file)
        self.assertIsNone(self.node.log_file_inode)

    def test_check_data_created(self):
        # create the file and write a line
        with open(self.dummy_file, 'wt') as f:
            print('hello', file=f)  # should be saved, wasn't there at init
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, [b'hello\n'])
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

        with open(self.dummy_file, 'at') as f:
            print('foo', file=f)  # will be saved, new in this run
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, [b'hello\n', b'foo\n'])
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

    def test_check_data_rolled(self):
        # create the file and write a line
        with open(self.dummy_file, 'wt') as f:
            print('hello', file=f)
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, [b'hello\n'])
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

        with open(self.dummy_file, 'at') as f:
            print('foo', file=f)  # will be saved, new in this run
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, [b'hello\n', b'foo\n'])
        self.assertIsNotNone(self.node.log_file)
        self.assertIsNotNone(self.node.log_file_inode)

        # write one last line to the old file
        with open(self.dummy_file, 'at') as f:
            print('bar', file=f)
        # rename the file, should persist inode
        rename(self.dummy_file, '{}.{}'.format(self.dummy_file, 1))

        # now create a new file
        with open(self.dummy_file, 'wt') as f:
            print('bye', file=f)  # should be saved, new file
        # first call should notice that the file has changed, grab the
        # remainder of the last file
        self.node.check_data(self.now)
        self.assertEqual(self.node.data, [b'hello\n', b'foo\n', b'bar\n'])
        # second call will grab the new file
        self.node.check_data(self.now)
        self.assertEqual(
            self.node.data,
            [b'hello\n', b'foo\n', b'bar\n', b'bye\n']
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
            [b'hello\n', b'foo\n', b'bar\n', b'bye\n', b'hi\n']
        )
        # because the file is rolling, no known next file exists
        self.assertIsNone(self.node.log_file)
        self.assertIsNone(self.node.log_file_inode)

    @patch('ona_service.log_watcher.logging', autospec=True)
    def test__set_fd(self, mock_logging):
        with open(self.dummy_file, 'w') as f:
            print('Here is a line', file=f)
            print('Here is another line', file=f)

        self.node._set_fd()
        inode1 = self.node.log_file_inode
        with open(self.dummy_file) as f:
            contents = f.read()
        self.assertEqual(self.node.log_file.read(), contents)

        self.node._set_fd(seek_to_end=True)
        inode2 = self.node.log_file_inode
        self.assertEqual(self.node.log_file.read(), '')
        self.assertEqual(inode1, inode2)

        log_args = mock_logging.info.call_args[0]
        log_message = log_args[0] % log_args[1:]
        self.assertIn('skipped 2 lines', log_message)

    def test_encoding(self):
        node = LogNode('one', None, self.dummy_file, encoding='cp1252')

        with open(self.dummy_file, 'wb') as f:
            f.write(b'Here\x9cs a line\n')

        node.check_data(self.now)

        actual = node.data[0]
        expected = b'Here\x9cs a line\n'
        self.assertEqual(actual, expected)

    def test_encoding_error(self):
        node = LogNode('one', None, self.dummy_file)

        with open(self.dummy_file, 'wb') as f:
            f.write(b'Here\x9cs a line\n')

        node.check_data(self.now)

        actual = node.data[0]
        expected = b'Heres a line\n'
        self.assertEqual(actual, expected)


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
    @patch('ona_service.log_watcher.LogNode', autospec=True)
    def test_LogWatcherInit(
        self,
        mock_LogNode,
        mock_SystemdJournalNode
    ):
        watcher = LogWatcher(
            logs={'log_name': 'log_path'},
            journals={'journal_name': ['SOME_FIELD=SOME_VALUE']},
        )
        self.assertEqual(len(watcher.log_nodes), 2)

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

    @patch('ona_service.log_watcher.LogNode', autospec=True)
    def test_service(self, mock_lognode):
        watcher = LogWatcher(
            logs={'auth.log': '/tmp', 'two': '/tmp/two'},
        )
        watcher.execute('now')
        lognode = mock_lognode.return_value
        self.assertEqual(lognode.check_data.call_count, 2)
        lognode.check_data.assert_called_with('now')

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
        self.temp_dir = TemporaryDirectory()

        def fixed_temp_file(*args, **kwargs):
            return NamedTemporaryFile(delete=False, dir=self.temp_dir.name)

        self.fixed_temp_file = fixed_temp_file

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_flush_data_compressed(self):
        patch_src = 'ona_service.log_watcher.NamedTemporaryFile'
        with patch(patch_src, self.fixed_temp_file):
            self.inst.flush_data(self.test_data, self.later, compress=True)

        # Gzip-read of the file should give back the input data
        for file_path in iglob(join(self.temp_dir.name, '*')):
            with gzip.open(file_path, 'rb') as infile:
                self.assertEqual(infile.read(), b''.join(self.test_data))

    def test_flush_data_uncompressed(self):
        patch_src = 'ona_service.log_watcher.NamedTemporaryFile'
        with patch(patch_src, self.fixed_temp_file):
            self.inst.flush_data(self.test_data, self.later)

        # Direct read of the file should give back the input data
        for file_path in iglob(join(self.temp_dir.name, '*')):
            with open(file_path) as infile:
                actual = infile.read()
            expected = b''.join(self.test_data).decode('utf-8')
            self.assertEqual(actual, expected)

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
