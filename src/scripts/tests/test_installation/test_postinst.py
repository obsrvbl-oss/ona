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
from unittest.mock import MagicMock, patch

from ona_service.installation import postinst

PATCH_PATH = 'ona_service.installation.postinst.{}'


class PostinstTestCase(TestCase):
    @patch(PATCH_PATH.format('system_tools'), autospec=True)
    def test_main(self, mock_system_tools):
        linux_type, linux_system = MagicMock(), MagicMock()
        linux_type.return_value = linux_system
        mock_system_tools.system_type = linux_type

        postinst.main('system_type')

        linux_system.stop_service.assert_called_once_with('obsrvbl-ona')
        linux_system.add_user.assert_called_once_with()
        linux_system.set_user_group.assert_called_once_with()
        linux_system.set_owner.assert_called_once_with()
        linux_system.set_sudoer.assert_called_once_with()
        linux_system.set_ona_name.assert_called_once_with()
        linux_system.install_services.assert_called_once_with()
        linux_system.start_service.assert_called_once_with('obsrvbl-ona')
