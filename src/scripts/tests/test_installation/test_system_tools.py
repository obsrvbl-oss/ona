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

from os.path import join
from unittest import TestCase

from mock import call as MockCall, mock_open, patch

from ona_service.installation import system_tools

PATCH_PATH = 'ona_service.installation.system_tools.{}'


class BaseSystemTestCase(TestCase):
    def setUp(self):
        self.base_system = system_tools.BaseSystem()

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
        # This is basically the function we're testing, but trust me: I typed
        # it out a second time.
        obsrvbl_user = system_tools.OBSRVBL_USER
        obsrvbl_root = system_tools.OBSRVBL_ROOT

        sudoers_path = join(obsrvbl_root, 'system', 'obsrvbl_ona.sudoers')
        tmp_path = join(obsrvbl_root, 'system', 'sudoers.tmp')
        command_list = (
            'grep {} /etc/sudoers > /dev/null'.format(obsrvbl_user),
            'cat /etc/sudoers {} > {}'.format(sudoers_path, tmp_path),
            'visudo -c -f {}'.format(tmp_path),
            'chown root:root {}'.format(tmp_path),
            'chmod 0440 {}'.format(tmp_path),
            'mv {} /etc/sudoers'.format(tmp_path),
        )

        def side_effect(*args, **kwargs):
            return 1 if args[0][0].startswith('grep') else 0

        mock_call.side_effect = side_effect
        self.base_system.set_sudoer()
        expected_calls = [MockCall([x], shell=True) for x in command_list]
        mock_call.assert_has_calls(expected_calls)

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_set_sudoer_exists(self, mock_call):
        # If the first call succeeds, ensure we bail out without further calls
        mock_call.return_value = 0
        self.base_system.set_sudoer()
        self.assertEqual(mock_call.call_count, 1)

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_set_user_group(self, mock_call):
        mock_call.set_user_group = 0
        self.base_system.set_user_group()
        command = 'usermod -a -G adm {}'.format(system_tools.OBSRVBL_USER)
        mock_call.assert_called_with(command.split(' '))


class SystemdMixinTestCase(TestCase):
    def setUp(self):
        # Create a class instance with the needed paths defined
        self.systemd_service_dir = '/tmp/usr/lib/systemd/system'
        self.systemd_startup_dir = '/tmp/etc/systemd/system'

        class SystemdSystem(system_tools.SystemdMixin):
            systemd_service_dir = self.systemd_service_dir
            systemd_startup_dir = self.systemd_startup_dir

        self.systemd_system = SystemdSystem()

    @patch(PATCH_PATH.format('call'), autospec=True)
    @patch(PATCH_PATH.format('symlink'), autospec=True)
    @patch(PATCH_PATH.format('copy'), autospec=True)
    @patch(PATCH_PATH.format('iglob'), autospec=True)
    def test_install_services(
        self, mock_iglob, mock_copy, mock_symlink, mock_call
    ):
        def _src(service):
            return join(system_tools.OBSRVBL_ROOT, 'system/systemd', service)

        def _dst(service):
            return join(self.systemd_service_dir, service)

        services = ['ona-test-service.service', 'obsrvbl-ona.service']
        mock_iglob.return_value = [_src(x) for x in services]

        self.systemd_system.install_services()

        # Make sure the right files were copied
        actual = mock_copy.call_args_list
        expected = [MockCall(_src(x), _dst(x)) for x in services]
        self.assertEqual(actual, expected)

        # Make sure the main service was symlinked
        mock_symlink.assert_called_once_with(
            _src('obsrvbl-ona.service'),
            join(self.systemd_startup_dir, 'obsrvbl-ona.service')
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


class SysVMixinTestCase(TestCase):
    def setUp(self):
        self.sysv_system = system_tools.SysVMixin()

    @patch(PATCH_PATH.format('call'), autospec=True)
    @patch(PATCH_PATH.format('copy'), autospec=True)
    def test_install_services(self, mock_copy, mock_call):
        open_ = mock_open()
        with patch(PATCH_PATH.format('open'), open_, create=True) as mocked:
            self.sysv_system.install_services()

        # inittab setup
        open_.assert_called_once_with('/etc/inittab', 'a')
        expected_calls = [
            MockCall(
                'ON:345:respawn:'
                '/bin/su -s /bin/sh -c '
                '"/opt/obsrvbl-ona/system/supervisord/ona-supervisord.sh" '
                'obsrvbl_ona'
            ),
            MockCall('\n'),
        ]
        mocked().write.assert_has_calls(expected_calls)

        # init q
        mock_call.assert_called_once_with('/sbin/init q'.split())

    def test_start_service(self):
        # Not implemented
        self.sysv_system.start_service('some_service')

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_stop_service(self, mock_call):
        mock_call.return_value = 0
        self.sysv_system.stop_service('some_service')
        expected_calls = [
            MockCall('sed -i s/ON:345.*//g /etc/inittab'.split()),
            MockCall('/sbin/init q'.split()),
        ]
        mock_call.assert_has_calls(expected_calls)


class UpstartTestCase(TestCase):
    def setUp(self):
        # Create a class instance with the needed paths defined
        self.upstart_startup_dir = '/tmp/etc/init'

        class UpstartSystem(system_tools.UpstartMixin):
            upstart_startup_dir = self.upstart_startup_dir

        self.upstart_system = UpstartSystem()

    @patch(PATCH_PATH.format('call'), autospec=True)
    @patch(PATCH_PATH.format('copy'), autospec=True)
    @patch(PATCH_PATH.format('iglob'), autospec=True)
    def test_install_services(self, mock_iglob, mock_copy, mock_call):
        def _src(service):
            return join(system_tools.OBSRVBL_ROOT, 'system/upstart', service)

        def _dst(service):
            return join(self.upstart_startup_dir, service)

        services = ['ona-test-service.conf', 'obsrvbl-ona.conf']
        mock_iglob.return_value = [_src(x) for x in services]

        self.upstart_system.install_services()

        # Make sure the right files were copied
        actual = mock_copy.call_args_list
        expected = [MockCall(_src(x), _dst(x)) for x in services]
        self.assertEqual(actual, expected)

        mock_call.assert_called_once_with(
            'initctl reload-configuration'.split()
        )

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_start_service(self, mock_call):
        service_name = 'ona-test-service'
        instance = ('key', 'value')

        # No instance specified
        mock_call.return_value = 0
        self.upstart_system.start_service(service_name)
        actual = ' '.join(mock_call.call_args[0][0])
        expected = 'sudo initctl start ona-test-service'
        self.assertEqual(actual, expected)

        # Instance tuple is specified
        mock_call.return_value = 0
        self.upstart_system.start_service(service_name, instance)
        actual = ' '.join(mock_call.call_args[0][0])
        expected = 'sudo initctl start ona-test-service key=value'
        self.assertEqual(actual, expected)

        # Service failed to start
        mock_call.return_value = 1
        with self.assertRaises(RuntimeError):
            self.upstart_system.start_service(service_name, instance)

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_stop_service(self, mock_call):
        service_name = 'ona-test-service'
        instance = ('key', 'value')

        # No instance specified
        self.upstart_system.stop_service(service_name)
        actual = ' '.join(mock_call.call_args[0][0])
        expected = 'sudo initctl stop ona-test-service'
        self.assertEqual(actual, expected)

        # Instance tuple is specified
        self.upstart_system.stop_service(service_name, instance)
        actual = ' '.join(mock_call.call_args[0][0])
        expected = 'sudo initctl stop ona-test-service key=value'
        self.assertEqual(actual, expected)

        # Check return code
        mock_call.return_value = 241
        actual = self.upstart_system.stop_service(service_name, instance)
        expected = 241
        self.assertEqual(actual, expected)


class BusyBoxMixinTestCase(TestCase):
    def setUp(self):
        self.busy_box = system_tools.BusyBoxMixin()

    @patch(PATCH_PATH.format('call'), autospec=True)
    @patch(PATCH_PATH.format('BusyBoxMixin.get_users'), autospec=True)
    def test_add_user(self, mock_get_users, mock_call):
        user_name = system_tools.OBSRVBL_USER
        # Try an already-existing user -> no calls
        mock_get_users.return_value = {user_name, 'pcapaldi'}
        self.busy_box.add_user()
        self.assertEqual(mock_call.call_count, 0)

        # No existing users -> add group and user
        mock_get_users.return_value = {'dtennant', 'msmith', 'pcapaldi'}
        self.busy_box.add_user()

        addgroup_args = 'addgroup -S {}'.format(user_name).split(' ')
        adduser_args = (
            'adduser -s /bin/false -G {0} -S -D -H {0}'.format(user_name)
        ).split(' ')
        expected_calls = [MockCall(addgroup_args), MockCall(adduser_args)]
        mock_call.assert_has_calls(expected_calls)

    @patch(PATCH_PATH.format('call'), autospec=True)
    def test_set_user_group(self, mock_call):
        self.busy_box.set_user_group()
        expected_args = (
            'addgroup {} adm'.format(system_tools.OBSRVBL_USER)
        ).split()
        mock_call.assert_called_once_with(expected_args)


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


class RHEL_5TestCase(TestCase):
    def setUp(self):
        self.rhel_5 = system_tools.RHEL_5()

    @patch(PATCH_PATH.format('call'), autospec=True)
    @patch(PATCH_PATH.format('RHEL_5.get_users'), autospec=True)
    def test_add_user(self, mock_get_users, mock_call):
        user_name = system_tools.OBSRVBL_USER
        # Try an already-existing user -> no calls
        mock_get_users.return_value = {user_name, 'pcapaldi'}
        self.rhel_5.add_user()
        self.assertEqual(mock_call.call_count, 0)

        # No existing users -> add group and user
        mock_get_users.return_value = {'dtennant', 'msmith', 'pcapaldi'}
        self.rhel_5.add_user()

        addgroup_args = 'groupadd -f -r {}'.format(user_name).split(' ')
        adduser_args = 'useradd -g {0} -d {1} -r -s /sbin/nologin {0}'.format(
            user_name, system_tools.OBSRVBL_ROOT
        ).split(' ')
        expected_calls = [MockCall(addgroup_args), MockCall(adduser_args)]
        mock_call.assert_has_calls(expected_calls)
