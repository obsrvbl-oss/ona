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

from mock import patch
from os import environ
from unittest import TestCase

from ona_service.iec61850_capturer import Iec61850Capturer
PATCH_PATH = 'ona_service.iec61850_capturer.{}'


class Iec61850CapturerTestCase(TestCase):
    def test_init(self):
        with patch.dict('os.environ'):
            environ['OBSRVBL_IEC61850_CAPTURE_SECONDS'] = '599'

            cap = Iec61850Capturer()

            self.assertEqual(
                cap.bpf_filter,
                'ether proto 0x88b8 or ether proto 0x88b9 '
                'or ether proto 0x88ba'
            )

            self.assertEqual(cap.capture_iface, 'any')
            self.assertEqual(cap.data_type, 'iec61850')
            self.assertEqual(cap.capture_seconds, 599)
