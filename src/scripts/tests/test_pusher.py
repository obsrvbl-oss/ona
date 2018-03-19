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
import signal

from datetime import datetime
from os import listdir, makedirs, remove
from os.path import exists, join
from shutil import rmtree
from tarfile import open as tar_open
from tempfile import gettempdir
from unittest import TestCase


from mock import call as MockCall, MagicMock, patch

from ona_service.pusher import Pusher, MAX_BACKLOG_DELTA
from ona_service.utils import utc


class PusherTestCase(TestCase):
    def setUp(self):
        self.inst = Pusher(data_type='test', poll_seconds=10)
        self.inst.api = MagicMock()
        self.utcnow = datetime.utcnow()

    def test_send_sensor_data(self):
        self.inst.api.send_file.return_value = '/data_path'
        self.inst.send_sensor_data('/some_path', self.utcnow)

        # Did we send the file?
        self.inst.api.send_file.assert_called_once_with(
            'test', '/some_path', self.utcnow.replace(tzinfo=utc)
        )

        # Did we send the signal?
        self.inst.api.send_signal.assert_called_once_with(
            data_type='sensordata',
            data={
                'timestamp': self.utcnow.replace(tzinfo=utc).isoformat(),
                'data_type': self.inst.data_type,
                'data_path': '/data_path',
            }
        )

    def test_get_file_datetime(self):
        # IPFIX style
        self.inst.file_fmt = '%Y%m%d%H%M'
        self.inst.prefix_len = 12
        actual = self.inst._get_file_datetime('201403241411')
        expected = datetime(2014, 3, 24, 14, 10, 0)
        self.assertEqual(actual, expected)

        # PNA style
        self.inst.file_fmt = 'pna-%Y%m%d%H%M'
        self.inst.prefix_len = 16
        actual = self.inst._get_file_datetime('pna-20140324141959-table0.log')
        expected = datetime(2014, 3, 24, 14, 10, 0)
        self.assertEqual(actual, expected)


class PusherTestBase(object):
    """
    Pusher child class tests (PNA, IPFIX) inherit from this class.
    """
    def _get_instance(self, cls, **kwargs):
        inst = cls(input_dir=join(gettempdir(), 'pusher_input'), **kwargs)
        inst.api = MagicMock()
        inst.api.ona_name = 'foo'
        inst.send_sensor_data = MagicMock()

        return inst

    def setUp(self):
        self.input_dir = self.inst.input_dir
        makedirs(self.input_dir)

        self.output_dir = self.inst.output_dir
        makedirs(self.output_dir)

        self.now = datetime(2014, 3, 24, 14, 20, 30)

    def tearDown(self):
        rmtree(self.input_dir, ignore_errors=True)
        rmtree(self.output_dir, ignore_errors=True)

    def test_execute(self):
        self._touch_files()
        self.inst.execute(self.now)

        # Did the heartbeat go out?
        self.inst.api.send_signal.assert_called_once_with(
            data_type='heartbeat',
            data={
                u'data_type': self.inst.data_type,
                u'sensor_hb_time': '2014-03-24T14:20:30+00:00',
            }
        )

        # Did the first group get deleted?
        input_paths = [join(self.input_dir, x) for x in self.ready[0:2]]
        self.assertFalse(any(exists(x) for x in input_paths))

        # Did the second group get deleted?
        input_paths = [join(self.input_dir, x) for x in self.ready[2:4]]
        self.assertFalse(any(exists(x) for x in input_paths))

        # The waiting group didn't get touched, did it?
        self.assertItemsEqual(listdir(self.input_dir), self.waiting)

        # Did we send the two groups?
        expected_calls = [
            MockCall(
                join(self.output_dir, self.output[0]),
                datetime(2014, 3, 24, 13, 50)
            ),
            MockCall(
                join(self.output_dir, self.output[1]),
                datetime(2014, 3, 24, 14, 0)
            ),
        ]
        self.assertEqual(
            self.inst.send_sensor_data.call_args_list, expected_calls
        )

        # Did we delete the two groups?
        self.assertItemsEqual(listdir(self.output_dir), [])

    def test_execute_backlog(self):
        # Everything the same as the normal execute() test, but the time is
        # later - enough later that we don't want to sendthe backlog.
        self._touch_files()
        self.inst.execute(self.now + MAX_BACKLOG_DELTA)

        # Ready files archived and deleted
        input_paths = [join(self.input_dir, x) for x in self.ready[0:2]]
        self.assertFalse(any(exists(x) for x in input_paths))

        input_paths = [join(self.input_dir, x) for x in self.ready[2:4]]
        self.assertFalse(any(exists(x) for x in input_paths))

        # Waiting items not touched
        self.assertItemsEqual(listdir(self.input_dir), self.waiting)

        # Nothing was sent, and the backlog was cleared
        self.assertEqual(self.inst.send_sensor_data.call_args_list, [])
        self.assertItemsEqual(listdir(self.output_dir), [])

    def test_execute_no_delete(self):
        self._touch_files()
        # If the sending failed...
        self.inst.send_sensor_data.return_value = False
        self.inst.execute(self.now)
        # Then the archives should not have been deleted
        self.assertItemsEqual(listdir(self.output_dir), self.output)
        # The tar files should still exist
        self.assertEqual(sorted(listdir(self.output_dir)), self.output)
        # The members should be as expected also
        file_path = join(self.output_dir, self.output[0])
        with tar_open(file_path, mode=self.tar_read_mode) as tarball:
            self.assertEqual(tarball.getnames(), self.ready[0:2])

        file_path = join(self.output_dir, self.output[1])
        with tar_open(file_path, mode=self.tar_read_mode) as tarball:
            self.assertEqual(tarball.getnames(), self.ready[2:4])

    @patch('ona_service.pusher.getsize', lambda x: 0)
    def test_execute_truncated(self):
        self._touch_files()
        self.inst.execute()
        # 0-length files should not attempt to send
        self.assertEqual(self.inst.send_sensor_data.call_count, 0)
        # They should also not be deleted
        self.assertItemsEqual(listdir(self.output_dir), self.output)

    @patch('ona_service.pusher.remove', autospec=True)
    def test_execute_ioerror(self, mock_remove):
        self._touch_files()
        # If we can't read one of the files...
        remove(join(self.input_dir, self.ready[0]))
        self.inst.execute(self.now)

        # ...it won't be added to the tar file.
        outfile_path = join(self.output_dir, self.output[0])
        with tar_open(outfile_path, mode=self.tar_read_mode) as tarball:
            self.assertItemsEqual(tarball.getnames(), self.ready[1:2])

    def test_service(self):
        self._touch_files()

        def killer(signum, frame):
            self.inst.stop()

        self.inst.poll_seconds = 0
        signal.signal(signal.SIGALRM, killer)
        signal.alarm(1)
        self.inst.run()

    def test_data_type(self):
        self._touch_files()
        self.assertEqual(self.inst.data_type, self.data_type)
