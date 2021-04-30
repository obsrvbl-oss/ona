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
from os.path import exists, join
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import call as MockCall, mock_open, patch
from uuid import uuid4

from ona_service.installation import system_tools

PATCH_PATH = 'ona_service.installation.system_tools.{}'


class BaseSystemTestCase(TestCase):
    def setUp(self):
        self.base_system = system_tools.BaseSystem()
        self.temp_dir = TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_users(self):
        read_data = 'one:x\ntwo:y\nthree:z'
        open_ = mock_open(read_data=read_data)
        with patch(PATCH_PATH.format('open'), open_, create=True) as mocked:
            mocked.return_value.__iter__.return_value = read_data.splitlines()
            users = self.base_system.get_users()

        self.assertEqual(users, {'one', 'two', 'three'})

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_set_owner(self, mock_call):
        obsrvbl_user = system_tools.OBSRVBL_USER
        obsrvbl_root = system_tools.OBSRVBL_ROOT

        # Success
        mock_call.return_value = 0
        commands = (
            'chown -R {0}:{0} {1}'.format(obsrvbl_user, obsrvbl_root),
            'chown root:root {}pna/user/pna'.format(obsrvbl_root),
        )
        expected_calls = [MockCall(x.split()) for x in commands]
        self.base_system.set_owner()
        mock_call.assert_has_calls(expected_calls)

        # Failure
        mock_call.return_value = 1
        with self.assertRaises(RuntimeError):
            self.base_system.set_owner()

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_set_sudoer(self, mock_call):
        sudoers_file_path = join(
            system_tools.OBSRVBL_ROOT, 'system', 'obsrvbl_ona.sudoers'
        )

        # Success
        mock_call.return_value = 0
        self.base_system.set_sudoer()
        commands = [
            'chown root {}'.format(sudoers_file_path),
            'chmod 0400 {}'.format(sudoers_file_path),
            'cp {} /etc/sudoers.d/obsrvbl_ona'.format(sudoers_file_path),
        ]
        mock_call.assert_has_calls([MockCall(x.split(' ')) for x in commands])

        # Failure
        mock_call.return_value = 1
        with self.assertRaises(RuntimeError):
            self.base_system.set_sudoer()

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_set_user_group(self, mock_call):
        self.base_system.set_user_group()
        command = 'usermod -a -G adm {}'.format(system_tools.OBSRVBL_USER)
        mock_call.assert_called_with(command.split(' '))

    @patch(PATCH_PATH.format('node'), autospec=True)
    def test_set_ona_name_default(self, mock_node):
        # The hostname is something we set, so we don't need to make one up.
        mock_node.return_value = 'ona-0a1b2c'
        with patch(PATCH_PATH.format('OBSRVBL_ROOT'), self.temp_dir.name):
            self.base_system.set_ona_name()

        # No configuration file should be written.
        config_local_path = join(self.temp_dir.name, 'config.local')
        self.assertFalse(exists(config_local_path))

    @patch(PATCH_PATH.format('uuid4'), autospec=True)
    @patch(PATCH_PATH.format('node'), autospec=True)
    def test_set_ona_name_override(self, mock_node, mock_uuid4):
        # The hostname is not something we set, so we make one up and write
        # it to the configuration file.
        mock_node.return_value = 'default'

        token = uuid4()
        mock_uuid4.return_value = token

        # Touch the config.local file
        config_local_path = join(self.temp_dir.name, 'config.local')
        with open(config_local_path, 'wt'):
            pass

        # Set the sensor name
        with patch(PATCH_PATH.format('OBSRVBL_ROOT'), self.temp_dir.name):
            self.base_system.set_ona_name()

        # Read back the configuration file
        with open(config_local_path) as infile:
            actual = infile.read()
        sensor_name = system_tools.ONA_NAME_PREFIX + str(token)[:6]
        expected = 'OBSRVBL_ONA_NAME="{}"\n'.format(sensor_name)
        self.assertEqual(actual, expected)

    @patch(PATCH_PATH.format('node'), autospec=True)
    def test_set_ona_name_no_override(self, mock_node):
        # The hostname is not something we set, but the configuration file
        # has already been written. So we don't override it.
        mock_node.return_value = 'default'

        sensor_name = system_tools.ONA_NAME_PREFIX + 'something'

        # Touch the config.local file
        config_local_path = join(self.temp_dir.name, 'config.local')
        with open(config_local_path, 'wt') as outfile:
            print('OBSRVBL_ONA_NAME="{}"'.format(sensor_name), file=outfile)

        # Set the sensor name
        with patch(PATCH_PATH.format('OBSRVBL_ROOT'), self.temp_dir.name):
            self.base_system.set_ona_name()

        # Read back the configuration file
        with open(config_local_path) as infile:
            actual = infile.read()
        expected = 'OBSRVBL_ONA_NAME="{}"\n'.format(sensor_name)
        self.assertEqual(actual, expected)


class SystemdMixinTestCase(TestCase):
    def setUp(self):
        self.systemd_system = system_tools.SystemdMixin()

    @patch(PATCH_PATH.format('call'), autospec=True)
    @patch(PATCH_PATH.format('copy'), autospec=True)
    def test_install_services(self, mock_copy, mock_call):
        self.systemd_system.install_services()

        # Make sure the right files were copied
        mock_copy.assert_called_once_with(
            join(
                system_tools.OBSRVBL_ROOT,
                'system/systemd',
                'obsrvbl-ona.service',
            ),
            '/etc/systemd/system/obsrvbl-ona.service'
        )

        # Make sure the systemctl calls were correct
        expected_calls = [
            MockCall(['systemctl', 'daemon-reload']),
            MockCall(['systemctl', 'enable', 'obsrvbl-ona.service']),
        ]
        mock_call.assert_has_calls(expected_calls)

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_start_service(self, mock_call):
        service_name = 'ona-test-service'
        instance = ('key', 'value')

        # No instance specified
        mock_call.return_value = 0
        self.systemd_system.start_service(service_name)
        actual = ' '.join(mock_call.call_args[0][0])
        expected = 'sudo systemctl start ona-test-service.service'
        self.assertEqual(actual, expected)

        # Instance tuple is specified
        mock_call.return_value = 0
        self.systemd_system.start_service(service_name, instance)
        actual = ' '.join(mock_call.call_args[0][0])
        expected = 'sudo systemctl start ona-test-service-@value.service'
        self.assertEqual(actual, expected)

        # Service failed to start
        mock_call.return_value = 1
        with self.assertRaises(RuntimeError):
            self.systemd_system.start_service(service_name, instance)

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_stop_service(self, mock_call):
        service_name = 'ona-test-service'
        instance = ('key', 'value')

        # No instance specified
        self.systemd_system.stop_service(service_name)
        actual = ' '.join(mock_call.call_args[0][0])
        expected = 'sudo systemctl stop ona-test-service.service'
        self.assertEqual(actual, expected)

        # Instance tuple is specified
        self.systemd_system.stop_service(service_name, instance)
        actual = ' '.join(mock_call.call_args[0][0])
        expected = 'sudo systemctl stop ona-test-service-@value.service'
        self.assertEqual(actual, expected)

        # Check return code
        mock_call.return_value = 241
        actual = self.systemd_system.stop_service(service_name, instance)
        expected = 241
        self.assertEqual(actual, expected)


class DebianMixinTestCase(TestCase):
    def setUp(self):
        self.debian = system_tools.DebianMixin()

    @patch(PATCH_PATH.format('call'), autospec=True)
    @patch(PATCH_PATH.format('DebianMixin.get_users'), autospec=True)
    def test_add_user(self, mock_get_users, mock_call):
        user_name = system_tools.OBSRVBL_USER
        # Try an already-existing user -> no calls
        mock_get_users.return_value = {user_name, 'pcapaldi'}
        self.debian.add_user()
        self.assertEqual(mock_call.call_count, 0)

        # No existing users -> add group and user
        mock_get_users.return_value = {'dtennant', 'msmith', 'pcapaldi'}
        self.debian.add_user()

        adduser_args = (
            'adduser --system --no-create-home --group --disabled-password {}'
        ).format(user_name).split(' ')
        expected_calls = [MockCall(adduser_args)]
        mock_call.assert_has_calls(expected_calls)


class RedHatMixinTestCase(TestCase):
    def setUp(self):
        self.red_hat = system_tools.RedHatMixin()

    @patch(PATCH_PATH.format('call'), autospec=True)
    @patch(PATCH_PATH.format('RedHatMixin.get_users'), autospec=True)
    def test_add_user(self, mock_get_users, mock_call):
        user_name = system_tools.OBSRVBL_USER
        # Try an already-existing user -> no calls
        mock_get_users.return_value = {user_name, 'pcapaldi'}
        self.red_hat.add_user()
        self.assertEqual(mock_call.call_count, 0)

        # No existing users -> add group and user
        mock_get_users.return_value = {'dtennant', 'msmith', 'pcapaldi'}
        self.red_hat.add_user()

        useradd_args = (
            'useradd -r -U -M -s /sbin/nologin {}'.format(user_name).split(' ')
        )
        expected_calls = [MockCall(useradd_args)]
        mock_call.assert_has_calls(expected_calls)
