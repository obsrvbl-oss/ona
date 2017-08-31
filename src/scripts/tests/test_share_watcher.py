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
import io

from datetime import datetime
from json import dumps
from os import environ, remove, stat
from os.path import join
from shutil import rmtree
from tempfile import mkdtemp
from unittest import TestCase

from mock import call as MockCall, MagicMock, mock_open, patch

from ona_service.share_watcher import ShareWatcher
from ona_service.utils import utc


def _append_line(file_path, line):
    with io.open(file_path, 'ab') as outfile:
        print(line, file=outfile, end='')


class ShareWatcherTestCase(TestCase):
    @patch('ona_service.share_watcher.get_ip', lambda *args: '192.0.2.241')
    def setUp(self):
        self.temp_dir = mkdtemp()
        self.log_path = join(self.temp_dir, 'samba_audit.log')
        self.now = datetime(2016, 3, 27, 18, 33, 16, tzinfo=utc)

        # Should be ignored by SambaAuditLogNode
        _append_line(self.log_path, 'Bogus\n')

        environ['OBSRVBL_SHARE_READ_ONLY'] = 'false'
        environ['OBSRVBL_SHARE_DIR'] = self.temp_dir
        environ['OBSRVBL_SHARE_FILE'] = 'README.txt'
        self.inst = ShareWatcher(log_path=self.log_path)
        self.inst.api = MagicMock()

    def tearDown(self):
        rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_contents(self):
        with io.open(self.inst.file_path, 'rt') as infile:
            contents = infile.read()

        all_lines = contents.splitlines()
        self.assertTrue(1 <= len(all_lines) <= 20)
        self.assertTrue(all(1 <= len(line) <= 79 for line in all_lines))
        self.assertTrue(all(0 <= ord(c) <= 255 for c in contents))

        # Make sure the file is writeable by users with access to the share
        self.assertEqual(stat(self.inst.file_path).st_mode & 0o777, 0o666)

    def test_no_change(self):
        # Unrelated write to the share directory
        _append_line(
            self.log_path,
            (
                'Mar 27 18:33:16 ona-7b09b4 smbd_audit: '
                '192.0.2.130|ie11win7|192.0.2.129|pwrite|ok|OTHER.txt\n'
            )
        )
        self.inst.execute()
        self.assertEqual(self.inst.log_node.data, [])
        self.assertEqual(self.inst.log_node.parsed_data, [])
        self.assertEqual(self.inst.api.send_file.call_count, 0)
        self.assertEqual(self.inst.api.send_signal.call_count, 0)

    @patch('ona_service.share_watcher.exit', autospec=True)
    def test_file_exist(self, mock_exit):
        _append_line(self.inst.file_path, '!')
        ShareWatcher(log_path=self.log_path)

    @patch('ona_service.share_watcher.exit', autospec=True)
    def test_change(self, mock_exit):
        # Writes to the target file
        unlink_line = (
            'Mar 27 18:33:16 ona-7b09b4 smbd_audit: '
            '192.0.2.130|ie11win7|192.0.2.129|unlink|ok|README.txt\n'
        )
        pwrite_line = (
            'Mar 27 18:33:16 ona-7b09b4 smbd_audit: '
            '192.0.2.130|ie11win7|192.0.2.129|pwrite|ok|README.txt\n'
        )
        for line in (unlink_line, pwrite_line):
            _append_line(self.log_path, line)

        _append_line(self.inst.file_path, '!')

        m = mock_open()
        mock_path = 'ona_service.utils.NamedTemporaryFile'
        with patch(mock_path, m, create=True):
            self.inst.execute(now=self.now)

        self.assertEqual(len(self.inst.log_node.data), 2)
        self.assertEqual(len(self.inst.log_node.parsed_data), 2)

        unlink_obs = {
            'observation_type': 'share_watcher_v1',
            'source': '192.0.2.241',
            'time': '2016-03-27T18:33:16+00:00',
            'connected_ip': '192.0.2.130',
            'connected_hostname': 'ie11win7',
            'operation': 'unlink',
            'argument': 'README.txt',
        }
        pwrite_obs = {
            'observation_type': 'share_watcher_v1',
            'source': '192.0.2.241',
            'time': '2016-03-27T18:33:16+00:00',
            'connected_ip': '192.0.2.130',
            'connected_hostname': 'ie11win7',
            'operation': 'pwrite',
            'argument': 'README.txt',
        }
        m.return_value.write.assert_has_calls(
            [
                MockCall(dumps(unlink_obs, sort_keys=True).encode('utf-8')),
                MockCall(b'\n'),
                MockCall(dumps(pwrite_obs, sort_keys=True).encode('utf-8')),
                MockCall(b'\n'),
            ]
        )
        self.assertEqual(self.inst.api.send_file.call_count, 1)
        self.assertEqual(self.inst.api.send_signal.call_count, 1)

        mock_exit.assert_called_once_with()

    @patch('ona_service.share_watcher.exit', autospec=True)
    def test_change_nologs(self, mock_exit):
        # Writes to the target file, but no logging
        _append_line(self.inst.file_path, '!')

        m = mock_open()
        mock_path = 'ona_service.utils.NamedTemporaryFile'
        with patch(mock_path, m, create=True):
            self.inst.execute(now=self.now)

        self.assertEqual(len(self.inst.log_node.data), 0)
        self.assertEqual(len(self.inst.log_node.parsed_data), 0)

        obs = {
            'observation_type': 'share_watcher_v1',
            'source': '192.0.2.241',
            'time': '2016-03-27T18:33:16+00:00',
            'connected_ip': None,
            'connected_hostname': None,
            'operation': None,
            'argument': 'README.txt',
        }
        m.return_value.write.assert_has_calls(
            [
                MockCall(dumps(obs, sort_keys=True).encode('utf-8')),
                MockCall(b'\n'),
            ]
        )
        self.assertEqual(self.inst.api.send_file.call_count, 1)
        self.assertEqual(self.inst.api.send_signal.call_count, 1)

        mock_exit.assert_called_once_with()

    @patch('ona_service.share_watcher.exit', autospec=True)
    def test_delete(self, mock_exit):
        unlink_line = (
            'Mar 27 18:33:16 ona-7b09b4 smbd_audit: '
            '192.0.2.130|ie11win7|192.0.2.129|unlink|ok|README.txt\n'
        )
        _append_line(self.log_path, unlink_line)

        remove(self.inst.file_path)

        m = mock_open()
        mock_path = 'ona_service.utils.NamedTemporaryFile'
        with patch(mock_path, m, create=True):
            self.inst.execute(now=self.now)

        self.assertEqual(len(self.inst.log_node.data), 1)
        self.assertEqual(len(self.inst.log_node.parsed_data), 1)

        unlink_obs = {
            'observation_type': 'share_watcher_v1',
            'source': '192.0.2.241',
            'time': '2016-03-27T18:33:16+00:00',
            'connected_ip': '192.0.2.130',
            'connected_hostname': 'ie11win7',
            'operation': 'unlink',
            'argument': 'README.txt',
        }
        m.return_value.write.assert_has_calls(
            [
                MockCall(dumps(unlink_obs, sort_keys=True).encode('utf-8')),
                MockCall(b'\n'),
            ]
        )
        self.assertEqual(self.inst.api.send_file.call_count, 1)
        self.assertEqual(self.inst.api.send_signal.call_count, 1)

        mock_exit.assert_called_once_with()


class ShareWatcherReadOnlyTestCase(TestCase):
    @patch('ona_service.share_watcher.get_ip', lambda *args: '192.0.2.241')
    def setUp(self):
        self.temp_dir = mkdtemp()
        self.log_path = join(self.temp_dir, 'samba_audit.log')
        self.now = datetime(2016, 3, 27, 18, 33, 16, tzinfo=utc)

        # Should be ignored by SambaAuditLogNode
        _append_line(self.log_path, 'Bogus\n')

        environ['OBSRVBL_SHARE_READ_ONLY'] = 'true'
        environ['OBSRVBL_SHARE_DIR'] = self.temp_dir
        file_name = 'remote_file.txt'
        environ['OBSRVBL_SHARE_FILE'] = file_name
        environ['OBSRVBL_SHARE_IP'] = '192.0.2.242'
        _append_line(join(self.temp_dir, file_name), 'Existing contents!\n')
        self.inst = ShareWatcher(log_path=self.log_path)
        self.inst.api = MagicMock()

    def tearDown(self):
        rmtree(self.temp_dir, ignore_errors=True)

    @patch('ona_service.share_watcher.exit', autospec=True)
    def test_read_only(self, mock_exit):
        _append_line(self.inst.file_path, 'Changes!')
        m = mock_open()
        mock_path = 'ona_service.utils.NamedTemporaryFile'
        with patch(mock_path, m, create=True):
            self.inst.execute(now=self.now)

        obs_data = {
            'observation_type': 'share_watcher_v1',
            'source': '192.0.2.242',
            'time': '2016-03-27T18:33:16+00:00',
            'connected_ip': None,
            'connected_hostname': None,
            'operation': None,
            'argument': 'remote_file.txt',
        }
        m.return_value.write.assert_has_calls(
            [
                MockCall(dumps(obs_data, sort_keys=True).encode('utf-8')),
                MockCall(b'\n'),
            ]
        )
        self.assertEqual(self.inst.api.send_file.call_count, 1)
        self.assertEqual(self.inst.api.send_signal.call_count, 1)

        mock_exit.assert_called_once_with()
