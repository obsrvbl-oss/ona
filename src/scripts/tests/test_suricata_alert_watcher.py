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
from __future__ import print_function

from datetime import datetime
import io
from glob import glob
from os import path, rename
from shutil import rmtree
from subprocess import CalledProcessError
from tempfile import mkdtemp
from unittest import TestCase

from mock import call, MagicMock, patch

from ona_service.suricata_alert_watcher import (
    _compress_log,
    SuricataAlertWatcher,
    MANAGE_SCRIPT,
    SURICATA_LOGNAME,
)


def dummy_get_ip():
    return '10.1.1.1'


def dummy_utcoffset():
    return 0


class SuricataAlertWatcherTest(TestCase):
    def setUp(self):
        self.tempdir = mkdtemp()

    def tearDown(self):
        rmtree(self.tempdir)

    @patch('ona_service.suricata_alert_watcher.check_call', autospec=True)
    def test_compress_log(self, mock_check_call):
        in_path = '/tmp/obsrvbl/eve.json.12345678.archived'
        out_path = '/tmp/obsrvbl/eve.json.12345678.archived.gz'

        # No error -> file is compressed
        self.assertEqual(_compress_log(in_path), out_path)

        # Error -> file is not compressed
        mock_check_call.side_effect = CalledProcessError(1, 'gzip')
        self.assertEqual(_compress_log(in_path), in_path)

        # Check for correct call
        expected_call = 'gzip -f {}'.format(in_path).split(' ')
        mock_check_call.assert_called_with(expected_call)

    @patch('ona_service.suricata_alert_watcher.check_output', autospec=True)
    def test_rotate_logs(self, mock_check_output):
        watcher = SuricataAlertWatcher()

        # Success
        mock_check_output.return_value = 0
        watcher._rotate_logs()
        mock_check_output.assert_called_once_with(
            ['sudo', '-u', 'suricata', MANAGE_SCRIPT, 'rotate-logs']
        )

        # Failure - don't die
        mock_check_output.side_effect = CalledProcessError(1, '')
        watcher._rotate_logs()

    @patch('ona_service.suricata_alert_watcher.get_ip', dummy_get_ip)
    @patch('ona_service.suricata_alert_watcher.utcoffset', dummy_utcoffset)
    def test_upload(self):
        file1 = self.tempdir + '/eve.json.foo.archived'
        file2 = self.tempdir + '/eve.json.bar.archived'
        ignored = self.tempdir + '/ignored'

        with open(file1, 'w'):
            pass
        with open(file2, 'w'):
            pass
        with open(ignored, 'w'):
            pass

        now = datetime(2015, 3, 12)
        watcher = SuricataAlertWatcher(log_dir=self.tempdir)
        watcher.api = MagicMock()
        watcher.api.send_file.return_value = 'send_destination'
        watcher._upload(now)

        self.assertFalse(path.exists(file1))
        self.assertFalse(path.exists(file2))
        self.assertTrue(path.exists(ignored))

        self.assertItemsEqual(watcher.api.send_file.call_args_list, [
            call('logs', file1, now, suffix='suricata'),
            call('logs', file2, now, suffix='suricata'),
        ])
        watcher.api.send_signal.assert_called_with('logs', {
            'path': 'send_destination',
            'utcoffset': 0,
            'log_type': 'suricata',
            'ip': '10.1.1.1',
        })
        self.assertEquals(len(watcher.api.send_signal.call_args_list), 2)

    def test_upload_compressed(self):
        watcher = SuricataAlertWatcher(log_dir=self.tempdir)
        watcher.api = MagicMock()

        # Write some fake data
        outfile_name = '{}.12345678.archived'.format(SURICATA_LOGNAME)
        outfile_path = path.join(self.tempdir, outfile_name)
        with io.open(outfile_path, 'w') as outfile:
            print(u'I am but a meer cat.', file=outfile)

        # Make the call
        now = datetime.now()
        watcher._upload(now, compress=True)

        # Ensure API calls are correct
        watcher.api.send_file.assert_called_once_with(
            'logs',
            '{}.gz'.format(outfile_path),
            now,
            suffix='suricata'
        )
        self.assertEqual(watcher.api.send_signal.call_count, 1)

        # Ensure that directory was cleaned up
        self.assertEqual(glob(path.join(self.tempdir, '*.*')), [])

    @patch('ona_service.suricata_alert_watcher.get_ip', dummy_get_ip)
    @patch('ona_service.suricata_alert_watcher.utcoffset', dummy_utcoffset)
    def test_upload_nothing(self):
        now = datetime(2015, 3, 12)
        watcher = SuricataAlertWatcher(log_dir=self.tempdir)
        watcher.api = MagicMock()
        watcher.api.send_file.return_value = 'send_destination'
        watcher._upload(now)

        self.assertEquals(watcher.api.send_file.call_args_list, [])
        self.assertEquals(watcher.api.call_args_list, [])

    @patch('ona_service.suricata_alert_watcher.get_ip', dummy_get_ip)
    @patch('ona_service.suricata_alert_watcher.utcoffset', dummy_utcoffset)
    @patch('ona_service.suricata_alert_watcher.check_output', autospec=True)
    def test_rotate_then_upload(self, mock_check_output):
        logfile = self.tempdir + '/eve.json'
        with open(logfile, 'w'):
            pass
        after_rename = '{}.{}.archived'.format(logfile, '12345678')

        mock_check_output.return_value = 0
        mock_check_output.side_effect = rename(logfile, after_rename)

        now = datetime(2015, 3, 12)
        watcher = SuricataAlertWatcher(log_dir=self.tempdir)
        watcher.api = MagicMock()
        watcher.api.send_file.return_value = 'send_destination'

        watcher._rotate_logs()
        self.assertFalse(path.exists(logfile))
        self.assertTrue(path.exists(after_rename))

        watcher._upload(now)
        self.assertFalse(path.exists(after_rename))

        self.assertEquals(watcher.api.send_file.call_args_list, [
            call('logs', after_rename, now, suffix='suricata'),
        ])
        self.assertEquals(watcher.api.send_signal.call_args_list, [
            call('logs', {
                'path': 'send_destination',
                'utcoffset': 0,
                'log_type': 'suricata',
                'ip': '10.1.1.1',
            })
        ])

    @patch('ona_service.suricata_alert_watcher.check_output', autospec=True)
    def test_update_rules(self, mock_check_output):
        watcher = SuricataAlertWatcher(log_dir=self.tempdir)
        watcher.api = MagicMock()
        watcher.api.get_data.return_value.iter_content.return_value = [
            'foo', 'bar', 'oof']

        my_rules = '{}/some.rules'.format(self.tempdir)
        with patch('ona_service.suricata_alert_watcher.SURICATA_RULE_PATH',
                   my_rules):
            watcher._update_rules()

        with open(my_rules, 'rb') as r:
            contents = r.read()
        self.assertEquals(contents, 'foobaroof')
        mock_check_output.assert_called_once_with(
            ['sudo', '-u', 'suricata', MANAGE_SCRIPT, 'reload-config']
        )
        watcher.api.get_data.assert_called_once_with('suricata-rules')

    @patch('ona_service.suricata_alert_watcher.SuricataAlertWatcher.'
           '_rotate_logs', autospec=True)
    @patch('ona_service.suricata_alert_watcher.SuricataAlertWatcher.'
           '_upload', autospec=True)
    @patch('ona_service.suricata_alert_watcher.SuricataAlertWatcher.'
           '_update_rules', autospec=True)
    def test_execute(self, mock_rules, mock_upload, mock_rotate_logs):
        watcher = SuricataAlertWatcher()

        now = datetime(2015, 1, 1)
        watcher.execute(now)

        mock_rotate_logs.assert_called_with(watcher)
        mock_upload.assert_called_with(watcher, now, compress=True)
        mock_rules.assert_called_with(watcher)

    @patch('ona_service.suricata_alert_watcher.utcnow', autospec=True)
    @patch('ona_service.suricata_alert_watcher.SuricataAlertWatcher.'
           '_rotate_logs', autospec=True)
    @patch('ona_service.suricata_alert_watcher.SuricataAlertWatcher.'
           '_upload', autospec=True)
    @patch('ona_service.suricata_alert_watcher.SuricataAlertWatcher.'
           '_update_rules', autospec=True)
    def test_execute_no_rules(self, mock_rules, mock_upload, mock_rotate_logs,
                              mock_utc):
        now = datetime(2015, 1, 1)
        mock_utc.return_value = now
        watcher = SuricataAlertWatcher()

        watcher.execute(now)

        mock_rotate_logs.assert_called_with(watcher)
        mock_upload.assert_called_with(watcher, now, compress=True)
        self.assertEquals(mock_rules.call_count, 0)
