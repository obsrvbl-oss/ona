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
from datetime import datetime
from glob import glob
from os import path, rename
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import call, MagicMock, patch

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


patch_path = 'ona_service.suricata_alert_watcher.{}'.format


class SuricataAlertWatcherTest(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch(patch_path('check_call'), autospec=True)
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

    @patch(patch_path('check_output'), autospec=True)
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

    @patch(patch_path('get_ip'), dummy_get_ip)
    @patch(patch_path('utcoffset'), dummy_utcoffset)
    def test_upload(self):
        file1 = path.join(self.temp_dir.name, 'eve.json.foo.archived')
        file2 = path.join(self.temp_dir.name, 'eve.json.bar.archived')
        ignored = path.join(self.temp_dir.name, 'ignored')

        with open(file1, 'w'):
            pass
        with open(file2, 'w'):
            pass
        with open(ignored, 'w'):
            pass

        now = datetime(2015, 3, 12)
        watcher = SuricataAlertWatcher(log_dir=self.temp_dir.name)
        watcher.api = MagicMock()
        watcher.api.send_file.return_value = 'send_destination'
        watcher._upload(now)

        self.assertFalse(path.exists(file1))
        self.assertFalse(path.exists(file2))
        self.assertTrue(path.exists(ignored))

        self.assertCountEqual(watcher.api.send_file.call_args_list, [
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
        watcher = SuricataAlertWatcher(log_dir=self.temp_dir.name)
        watcher.api = MagicMock()

        # Write some fake data
        outfile_name = '{}.12345678.archived'.format(SURICATA_LOGNAME)
        outfile_path = path.join(self.temp_dir.name, outfile_name)
        with open(outfile_path, 'w') as outfile:
            print('I am but a meer cat.', file=outfile)

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
        self.assertEqual(glob(path.join(self.temp_dir.name, '*.*')), [])

    @patch(patch_path('get_ip'), dummy_get_ip)
    @patch(patch_path('utcoffset'), dummy_utcoffset)
    def test_upload_nothing(self):
        now = datetime(2015, 3, 12)
        watcher = SuricataAlertWatcher(log_dir=self.temp_dir.name)
        watcher.api = MagicMock()
        watcher.api.send_file.return_value = 'send_destination'
        watcher._upload(now)

        self.assertEquals(watcher.api.send_file.call_args_list, [])
        self.assertEquals(watcher.api.call_args_list, [])

    @patch(patch_path('get_ip'), dummy_get_ip)
    @patch(patch_path('utcoffset'), dummy_utcoffset)
    @patch(patch_path('check_output'), autospec=True)
    def test_rotate_then_upload(self, mock_check_output):
        logfile = path.join(self.temp_dir.name, 'eve.json')
        with open(logfile, 'w'):
            pass
        after_rename = '{}.{}.archived'.format(logfile, '12345678')

        mock_check_output.return_value = 0
        mock_check_output.side_effect = rename(logfile, after_rename)

        now = datetime(2015, 3, 12)
        watcher = SuricataAlertWatcher(log_dir=self.temp_dir.name)
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

    @patch(patch_path('check_output'), autospec=True)
    def test_update_rules(self, mock_check_output):
        watcher = SuricataAlertWatcher(log_dir=self.temp_dir.name)
        watcher.api = MagicMock()
        watcher.api.get_data.return_value.iter_content.return_value = [
            b'foo', b'bar', b'oof'
        ]

        my_rules = '{}/some.rules'.format(self.temp_dir.name)
        with patch(patch_path('SURICATA_RULE_PATH'), my_rules):
            watcher._update_rules()

        with open(my_rules) as r:
            contents = r.read()

        self.assertEquals(contents, 'foobaroof')
        mock_check_output.assert_called_once_with(
            ['sudo', '-u', 'suricata', MANAGE_SCRIPT, 'reload-config']
        )
        watcher.api.get_data.assert_called_once_with('suricata-rules')

    @patch(patch_path('SuricataAlertWatcher._rotate_logs'), autospec=True)
    @patch(patch_path('SuricataAlertWatcher._upload'), autospec=True)
    @patch(patch_path('SuricataAlertWatcher._update_rules'), autospec=True)
    def test_execute(self, mock_rules, mock_upload, mock_rotate_logs):
        watcher = SuricataAlertWatcher()

        # Rules exist
        rule_path = path.join(self.temp_dir.name, 'downloaded.rules')
        with open(rule_path, 'wb') as outfile:
            outfile.write(b'rule_data\n')

        # 2015 was a long time ago, so it's time to update
        with patch(patch_path('SURICATA_RULE_PATH'), rule_path):
            now = datetime(2015, 1, 1)
            watcher.execute(now)

        mock_rotate_logs.assert_called_with(watcher)
        mock_upload.assert_called_with(watcher, now, compress=True)
        mock_rules.assert_called_with(watcher)

    @patch(patch_path('utcnow'), autospec=True)
    @patch(patch_path('SuricataAlertWatcher._rotate_logs'), autospec=True)
    @patch(patch_path('SuricataAlertWatcher._upload'), autospec=True)
    @patch(patch_path('SuricataAlertWatcher._update_rules'), autospec=True)
    def test_execute_no_rules(
        self, mock_rules, mock_upload, mock_rotate_logs, mock_utc
    ):
        watcher = SuricataAlertWatcher()

        rule_path = path.join(self.temp_dir.name, 'downloaded.rules')

        # 2015 is now, according to this test, so it's not time to update.
        # However, the rule file doesn't exist - so we will.
        now = datetime(2015, 1, 1)
        mock_utc.return_value = now
        with patch(patch_path('SURICATA_RULE_PATH'), rule_path):
            watcher.execute(now)

        mock_rotate_logs.assert_called_with(watcher)
        mock_upload.assert_called_with(watcher, now, compress=True)
        self.assertEquals(mock_rules.call_count, 1)

    @patch(patch_path('check_output'), autospec=True)
    def test_execute_no_suricata(self, mock_check_output):
        watcher = SuricataAlertWatcher()
        watcher.api = MagicMock()

        # It's time to update, but the rule directory doesn't exist.
        # So we won't.
        rule_path = path.join(
            self.temp_dir.name, 'different-dir/downloaded.rules'
        )
        with patch(patch_path('SURICATA_RULE_PATH'), rule_path):
            now = datetime(2015, 1, 1)
            watcher.execute(now)

        self.assertFalse(watcher.api.mock_calls)
