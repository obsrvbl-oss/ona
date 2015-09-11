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
from os.path import join
from tempfile import gettempdir

# local
from tcpdump_capturer import TcpdumpCapturer


class ArpCapturer(TcpdumpCapturer):
    def __init__(self, *args, **kwargs):
        init_kwargs = {
            'bpf_filter': 'arp',
            'data_type': 'arp',
            'capture_iface': getenv('OBSRVBL_ARP_CAPTURE_IFACE', 'any'),
            'capture_seconds': int(
                getenv('OBSRVBL_ARP_CAPTURE_SECONDS', '600')
            ),
            'pcap_dir': join(
                gettempdir(), getenv('OBSRVBL_ARP_PCAP_DIR', 'obsrvbl_arp')
            ),
            'poll_seconds': 600,
            'pps_limit': int(getenv('OBSRVBL_ARP_PPS_LIMIT', '100')),
        }
        kwargs.update(init_kwargs)
        super(ArpCapturer, self).__init__(*args, **kwargs)


if __name__ == '__main__':
    capturer = ArpCapturer()
    capturer.run()
