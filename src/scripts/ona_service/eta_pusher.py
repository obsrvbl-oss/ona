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
from __future__ import division, print_function, unicode_literals

# python builtins
from os import getenv

# local
from tcpdump_pusher import TcpdumpPusher

ENV_ETA_PCAP_DIR = 'OBSRVBL_ETA_PCAP_DIR'
DEFAULT_ETA_PCAP_DIR = './logs'


class EtaPusher(TcpdumpPusher):
    def __init__(self, *args, **kwargs):
        init_kwargs = {
            'data_type': 'logs',
            'poll_seconds': 60,
            'pcap_dir': getenv(ENV_ETA_PCAP_DIR, DEFAULT_ETA_PCAP_DIR),
        }
        kwargs.update(init_kwargs)
        super(EtaPusher, self).__init__(*args, **kwargs)

    def execute(self, now=None):
        all_remote_paths = super(EtaPusher, self).execute(now=now)

        for remote_path in all_remote_paths:
            self.api.send_signal(
                self.data_type,
                data={'path': remote_path, 'log_type': 'eta-pcap'}
            )


if __name__ == '__main__':
    EtaPusher().run()
