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
from __future__ import division, print_function, unicode_literals

# python builtins
from os import getenv

# local
from tcpdump_pusher import TcpdumpPusher

ENV_PDNS_PCAP_DIR = 'OBSRVBL_PDNS_PCAP_DIR'
DEFAULT_PDNS_PCAP_DIR = './logs'


class PdnsPusher(TcpdumpPusher):
    def __init__(self, *args, **kwargs):
        init_kwargs = {
            'data_type': 'pdns',
            'poll_seconds': 600,
            'pcap_dir': getenv(ENV_PDNS_PCAP_DIR, DEFAULT_PDNS_PCAP_DIR),
        }
        kwargs.update(init_kwargs)
        super(PdnsPusher, self).__init__(*args, **kwargs)


if __name__ == '__main__':
    PdnsPusher().run()
