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

from unittest import TestCase

from ona_service.service import Service


class AwesomeAndTotallySweetService(Service):
    def __init__(self):
        kwargs = {
            'data_type': 'datum',
            'poll_seconds': 0,
        }
        super(AwesomeAndTotallySweetService, self).__init__(**kwargs)
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
