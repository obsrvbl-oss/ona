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
from unittest import TestCase
from unittest.mock import Mock, patch

from ona_service.service import Service


class AwesomeAndTotallySweetService(Service):
    def __init__(self, **kwargs):
        kwargs.setdefault('data_type', 'datum')
        kwargs.setdefault('poll_seconds', 0)
        super().__init__(**kwargs)
        self.called = False

    def execute(self, now=None):
        self.called = True


class ServiceTestCase(TestCase):
    def test_thread(self):
        service = AwesomeAndTotallySweetService()

        def killer(signum, frame):
            service.stop()
        signal.signal(signal.SIGALRM, killer)
        signal.alarm(1)

        service.run()

        self.assertTrue(service.called)

    @patch('ona_service.service.utcnow', autospec=True)
    @patch('ona_service.service.sleep', autospec=True)
    def test_sleep(self, mock_sleep, mock_utcnow):
        t1 = datetime(2015, 10, 1, 1, 30)
        t2 = datetime(2015, 10, 1, 1, 30)
        mock_utcnow.side_effect = [t1, t2]

        service = AwesomeAndTotallySweetService(poll_seconds=30)
        service.stop_event = Mock()
        service.stop_event.is_set.side_effect = [False, False, True]

        service.run()

        self.assertTrue(service.called)
        mock_sleep.assert_called_once_with(30)

    @patch('ona_service.service.utcnow', autospec=True)
    @patch('ona_service.service.sleep', autospec=True)
    def test_sleep__short(self, mock_sleep, mock_utcnow):
        t1 = datetime(2015, 10, 1, 1, 30)
        t2 = datetime(2015, 10, 1, 1, 30, 3)
        mock_utcnow.side_effect = [t1, t2]

        service = AwesomeAndTotallySweetService(poll_seconds=30)
        service.stop_event = Mock()
        service.stop_event.is_set.side_effect = [False, False, True]

        service.run()

        self.assertTrue(service.called)
        mock_sleep.assert_called_once_with(27)  # 30 - 3

    @patch('ona_service.service.utcnow', autospec=True)
    @patch('ona_service.service.sleep', autospec=True)
    def test_sleep__long_execute(self, mock_sleep, mock_utcnow):
        t1 = datetime(2015, 10, 1, 1, 30)
        t2 = datetime(2015, 10, 1, 1, 30, 31)
        mock_utcnow.side_effect = [t1, t2]

        service = AwesomeAndTotallySweetService(poll_seconds=30)
        service.stop_event = Mock()
        service.stop_event.is_set.side_effect = [False, False, True]

        service.run()

        self.assertTrue(service.called)
        # if we take more than poll_seconds to run the job, sleep(0) and jump
        # right back in.
        mock_sleep.assert_called_once_with(0)
