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
from os.path import join
from unittest import TestCase

from ona_service.pna_pusher import PnaPusher

from tests.test_pusher import PusherTestBase


class PnaPusherTestCase(PusherTestBase, TestCase):
    def setUp(self):
        self.data_type = 'pna'
        self.inst = self._get_instance(PnaPusher)
        self.tar_read_mode = 'r:bz2'
        super(PnaPusherTestCase, self).setUp()

    def _touch_files(self):
        # Files ready for processing
        self.ready = [
            'pna-20140324135000-table0.log',
            'pna-20140324135959-table0.log',
            'pna-20140324140000-table0.log',
            'pna-20140324140959-table0.log',
        ]

        # Files still in use
        self.waiting = [
            'pna-20140324141000-table0.log',
            'pna-20140324141130-table0.log',
            'pna-20140324141959-table0.log',
        ]

        # Files created by tar
        self.output = [
            'pna-201403241350.foo',
            'pna-201403241400.foo',
        ]

        # Touch all the input files
        for file_name in (self.ready + self.waiting):
            file_path = join(self.input_dir, file_name)
            open(file_path, 'w').close()

        # Touch all the output file
        for file_name in self.output:
            file_path = join(self.output_dir, file_name)
            open(file_path, 'w').close()
