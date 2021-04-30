#  Copyright 2018 Observable Networks
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
from os import listdir
from os.path import join
from shutil import rmtree
from unittest import TestCase
from unittest.mock import call as MockCall, MagicMock

from ona_service.eta_pusher import EtaPusher


class EtaPusherTestCase(TestCase):
    def setUp(self):
        self.inst = EtaPusher()
        self.inst.api = MagicMock()
        self.inst.api.send_file.side_effect = (
            lambda *args, **kwargs: 'file:///tmp/{}/{}/{}'.format(*args)
        )

    def tearDown(self):
        rmtree(self.inst.pcap_dir)

    def test_eta_pusher(self):
        # Touch some pcap files
        for n in (1, 2, 3):
            file_path = join(self.inst.pcap_dir, 'logs_{}.pcap'.format(n))
            with open(file_path, 'wb'):
                pass

        now = datetime(2018, 4, 16, 14, 9, 33)
        self.inst.execute(now=now)

        # All but the most recent file should have been cleared out
        self.assertEqual(
            sorted(listdir(self.inst.pcap_dir)), ['logs_3.pcap']
        )

        # Send file should have been called on each file
        path_1 = join(self.inst.pcap_dir, 'logs_1.pcap.gz')
        path_2 = join(self.inst.pcap_dir, 'logs_2.pcap.gz')
        dt = datetime(2018, 4, 16, 14, 0, 0)
        self.inst.api.send_file.assert_has_calls(
            [
                MockCall('logs', path_1, dt, suffix='0000'),
                MockCall('logs', path_2, dt, suffix='0001'),
            ],
            any_order=True
        )

        # Send signal should have been called for each file
        for args, kwargs in self.inst.api.send_signal.call_args_list:
            self.assertEqual(args, ('logs',))
            self.assertEqual(kwargs['data']['log_type'], 'eta-pcap')
