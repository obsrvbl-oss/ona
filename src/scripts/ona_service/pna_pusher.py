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

from os import getenv

# local
from pusher import Pusher

# determine compression to use for transfer
try:
    import bz2  # noqa
    TAR_MODE = 'w:bz2'
except ImportError:
    import gzip  # noqa
    TAR_MODE = 'w:gz'

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

ENV_PNA_LOGDIR = 'PNA_LOGDIR'
DEFAULT_PNA_LOGDIR = './logs'
POLL_SECONDS = 30


class PnaPusher(Pusher):
    """
    The PNA software writes logs every 10 seconds.  These are aggregated on
    ten minute intervals (HHMs), compressed, and written to the Observable
    cloud for processing.
    """

    def __init__(self, *args, **kwargs):
        kwargs.update({
            'data_type': 'pna',
            'file_fmt': 'pna-%Y%m%d%H%M',
            'prefix_len': 16,
            'input_dir': getenv(ENV_PNA_LOGDIR, DEFAULT_PNA_LOGDIR),
            'poll_seconds': POLL_SECONDS,
        })

        # archives will be compressed before transmission
        self.tar_mode = TAR_MODE

        super(PnaPusher, self).__init__(*args, **kwargs)

if __name__ == '__main__':
    pusher = PnaPusher()
    pusher.run()
