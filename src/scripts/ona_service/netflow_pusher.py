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
from __future__ import print_function, unicode_literals

# python builtins
import logging

from os import getenv, remove
from os.path import join, split
from shutil import copy
from subprocess import call

# local
from pusher import Pusher

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

ENV_NETFLOW_LOGDIR = 'OBSRVBL_NETFLOW_LOGDIR'
DEFAULT_NETFLOW_LOGDIR = './logs'
POLL_SECONDS = 30

ENV_MONITOR_NETS = 'OBSRVBL_NETWORKS'
DEFAULT_MONITOR_NETS = "10.0.0.0/8 172.16.0.0/12 192.168.0.0/16"


class NetflowPusher(Pusher):
    """Combines NetFlow data into 10 minute segments and send them to
    Observable Networks.
    """

    def __init__(self, *args, **kwargs):
        kwargs.update({
            'file_fmt': 'nfcapd.%Y%m%d%H%M',
            'prefix_len': 19,
            'data_type': 'netflow',
            'input_dir': getenv(ENV_NETFLOW_LOGDIR, DEFAULT_NETFLOW_LOGDIR),
            'poll_seconds': POLL_SECONDS,
        })

        # set up the subnet filter
        monitor_nets = getenv(ENV_MONITOR_NETS, DEFAULT_MONITOR_NETS)
        net_list = ['(net {})'.format(x) for x in monitor_nets.split()]
        self.net_filter = ' or '.join(net_list)

        # archives will be compressed by nfcapd
        self.tar_mode = 'w'

        super(NetflowPusher, self).__init__(*args, **kwargs)

    def _process_files(self, file_list):
        """
        Run nfdump to filter out unmonitored networks.
        """
        for file_path in file_list:
            file_dir, file_name = split(file_path)
            temp_path = join(file_dir, '{}.tmp'.format(file_name))
            copy(file_path, temp_path)
            command = [
                'nfdump',
                '-r', temp_path,
                '-w', file_path,
                '-z',
                self.net_filter,
            ]
            return_code = call(command)
            if return_code:
                logging.warning('Error processing %s', file_path)

            remove(temp_path)


if __name__ == '__main__':
    pusher = NetflowPusher()
    pusher.run()
