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
from unittest import TestCase
from mock import patch

from ona_service.ossec_alert_watcher import (
    WATCH_LOGS,
    SEND_DELTA,
    run_ossec_alert_log_watcher,
)


class RunOssecAlertLogWatcherTestCase(TestCase):
    @patch('ona_service.ossec_alert_watcher.LogWatcher', autospec=True)
    def test_runs_log_watcher(self, MockWatcher):
        instance = MockWatcher.return_value
        run_ossec_alert_log_watcher()
        MockWatcher.assert_called_once_with(
            logs=WATCH_LOGS,
            send_delta=SEND_DELTA
        )
        instance.run.assert_called_once_with()
