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

from glob import iglob
from io import open
from os import symlink
from os.path import basename, join
from shutil import copy
from subprocess import call

OBSRVBL_ROOT = '/opt/obsrvbl-ona/'
OBSRVBL_USER = 'obsrvbl_ona'


class BaseSystem(object):
    def add_user(self):
        """
        Adds a system user that preferably doesn't have a home directory,
        password, or shell in the distribution-appropriate method. Assign it
        to a group with the same name.
        """
        raise NotImplementedError

    def get_users(self):
        """
        Retrieves the set of users from /etc/passwd
        """
        with open('/etc/passwd', 'r') as infile:
            users = {x.split(':')[0] for x in infile}

        return users

    def install_services(self):
        """
        Copies the ONA service files to the init system-appropriate locations.
        """
        raise NotImplementedError

    def set_owner(self):
        """
        Sets the ONA service directory to be owned by the ONA user and group.
        Raises RuntimeError if something fails.
        """
        user_group = '{}:{}'.format(OBSRVBL_USER, OBSRVBL_USER)
        pna_path = join(OBSRVBL_ROOT, 'pna/user/pna')

        for args in (
            ['chown', '-R', user_group, OBSRVBL_ROOT],
            ['chown', 'root:root', pna_path],
        ):
            return_code = call(args)

            if return_code != 0:
                msg = 'Failed during: {}'.format(' '.join(args))
                raise RuntimeError(msg)

    def set_user_group(self):
        """
        Adds the ONA user to the adm group so it can read the system logs.
        """
        call(['usermod', '-a', '-G', 'adm', OBSRVBL_USER])

    def set_sudoer(self):
        """
        Allows the ONA user to execute certain commands as root, sans password.
        This is crazy dangerous, so we use visudo to ensure that the changes we
        make are valid.
        """
        # Step 0: Check to see if the obsrvbl_ona entries are already present
        command = 'grep {} /etc/sudoers > /dev/null'.format(OBSRVBL_USER)
        return_code = call([command], shell=True)
        if return_code == 0:
            print('{} is already in /etc/sudoers'.format(OBSRVBL_USER))
            return

        # Step 1: Concatenate the original file and our additions to a
        # new file.
        # Step 2: Use visudo to check that the new file is valid.
        # Step 3: Verify that the new file is owned by the root user and group
        # Step 4: Set the new file's read/write/execute permissions to 0440
        # Step 5: Replace the original file
        sudoers_path = join(OBSRVBL_ROOT, 'system', 'obsrvbl_ona.sudoers')
        tmp_path = join(OBSRVBL_ROOT, 'system', 'sudoers.tmp')
        for command in (
            'cat /etc/sudoers {} > {}'.format(sudoers_path, tmp_path),
            'visudo -c -f {}'.format(tmp_path),
            'chown root:root {}'.format(tmp_path),
            'chmod 0440 {}'.format(tmp_path),
            'mv {} /etc/sudoers'.format(tmp_path),
        ):
            return_code = call([command], shell=True)

            if return_code != 0:
                print('Failed during: {}'.format(command))
                return

    def start_service(self, service_name, instance=None):
        """
        Start the service given by `service_name` with the proper init system
        call. Optionally specify an `instance` tuple to stop a service with
        multiple instances.
        Returns RuntimeError if the service fails to start.
        """
        raise NotImplementedError

    def stop_service(self, service_name, instance=None):
        """
        Stop the service given by `service_name` with the proper init system
        call. Optionally specify an `instance` tuple to stop a service with
        multiple instances.
        Returns the return code from the stopping command.
        """
        raise NotImplementedError


# Init system mixins

class SystemdMixin(BaseSystem):
    @property
    def systemd_service_dir(self):
        raise NotImplementedError

    @property
    def systemd_startup_dir(self):
        raise NotImplementedError

    def _get_service_name(self, service_name, instance=None):
        """
        Appends ".service" to `service_name` if `instance` is None.
        Appends "-@value.service" if an `instance` tuple (key, value)
        is specified.
        """
        if instance is not None:
            key, value = instance
            return '{}-@{}.service'.format(service_name, value)

        return '{}.service'.format(service_name)

    def _systemctl(self, action, service_name):
        """
        Calls sudo systemctl action service_name key=value
        `action` is "start" or "stop"
        `service_name` is the name of an ONA service.
        Returns the return code from systemctl.
        """
        return call(['sudo', 'systemctl', action, service_name])

    def install_services(self):
        # Copy the service files to the systemd service directory
        pattern = join(OBSRVBL_ROOT, 'system/systemd/*.service')
        for src_path in iglob(pattern):
            dst_path = join(self.systemd_service_dir, basename(src_path))
            copy(src_path, dst_path)

        # Symlink the ONA service file to the startup directory
        link_source = join(
            OBSRVBL_ROOT, 'system/systemd/obsrvbl-ona.service'
        )
        link_name = join(
            self.systemd_startup_dir, 'obsrvbl-ona.service'
        )
        symlink(link_source, link_name)

        # Register the main ONA service
        call(['systemctl', 'daemon-reload'])
        call(['systemctl', 'enable', 'obsrvbl-ona.service'])

    def start_service(self, service_name, instance=None):
        service_name = self._get_service_name(service_name, instance)
        return_code = self._systemctl('start', service_name)

        if return_code != 0:
            err_msg = 'Error starting {}. initctl returned {}'.format(
                service_name, return_code
            )
            raise RuntimeError(err_msg)

    def stop_service(self, service_name, instance=None):
        service_name = self._get_service_name(service_name, instance)
        return_code = self._systemctl('stop', service_name)

        return return_code


class SysVMixin(BaseSystem):
    def install_services(self):
        # Keep Supervisor running
        script_path = join(
            OBSRVBL_ROOT, 'system/supervisord', 'ona-supervisord.sh'
        )
        command = '/bin/su -s /bin/sh -c "{}" {}'.format(
            script_path, OBSRVBL_USER
        )
        inittab_line = 'ON:345:respawn:{}'.format(command)

        with open('/etc/inittab', 'a') as outfile:
            print(inittab_line, file=outfile)

        # Start the service for the first time
        call(['/sbin/init', 'q'])

    def start_service(self, service_name, instance=None):
        # Not implemented
        pass

    def stop_service(self, service_name, instance=None):
        for args in (
            ['sed', '-i', 's/ON:345.*//g', '/etc/inittab'],
            ['/sbin/init', 'q'],
        ):
            return_code = call(args)

            if return_code != 0:
                print('Failed during: {}'.format(' '.join(args)))
                return


class UpstartMixin(BaseSystem):
    obsrvbl_upstart_dir = join(OBSRVBL_ROOT, 'system/upstart')
    upstart_startup_dir = '/etc/init'

    def _initctl(self, action, service_name, instance=None):
        """
        Calls sudo initctl action service_name key=value
        `action` is "start" or "stop"
        `service_name` is the name of an ONA service
        `instance` is a (key, value) tuple like ("eth", "eth1")
        Returns the return code from initctl.
        """
        args = ['sudo', 'initctl', action, service_name]
        if instance is not None:
            key, value = instance
            args.append('{}={}'.format(key, value))

        return call(args)

    def install_services(self):
        # Copy the service files to the upstart startup directory
        pattern = join(self.obsrvbl_upstart_dir, '*.conf')
        for src_path in iglob(pattern):
            dst_path = join(self.upstart_startup_dir, basename(src_path))
            copy(src_path, dst_path)

        # Register the services
        call(['initctl', 'reload-configuration'])

    def start_service(self, service_name, instance=None):
        return_code = self._initctl('start', service_name, instance)

        if return_code != 0:
            err_msg = 'Error starting {}. initctl returned {}'.format(
                service_name, return_code
            )
            raise RuntimeError(err_msg)

    def stop_service(self, service_name, instance=None):
        return_code = self._initctl('stop', service_name, instance)

        return return_code


# Distro-style mixins

class BusyBoxMixin(BaseSystem):
    def add_user(self):
        # Don't create a user that already exists
        if OBSRVBL_USER in self.get_users():
            return

        # Create the system group
        call(['addgroup', '-S', OBSRVBL_USER])

        args = [
            'adduser',
            '-s', '/bin/false',  # No shell access allowed
            '-G', OBSRVBL_USER,  # Assign to the system group
            '-S',  # Create a system user
            '-D',  # Do not assign a password
            '-H',  # Do not create home directory
            OBSRVBL_USER
        ]
        call(args)

    def set_user_group(self):
        call(['addgroup', OBSRVBL_USER, 'adm'])


class DebianMixin(BaseSystem):
    def add_user(self):
        # Don't create a user that already exists
        if OBSRVBL_USER in self.get_users():
            return

        args = [
            'adduser',
            '--system',
            '--no-create-home',
            '--group',
            '--disabled-password',
            OBSRVBL_USER
        ]
        call(args)


class RedHatMixin(BaseSystem):
    dummy_shell = '/sbin/nologin'

    def add_user(self):
        # Don't create a user that already exists
        if OBSRVBL_USER in self.get_users():
            return

        args = [
            'useradd',
            '-r',  # System user
            '-U',  # Create a group with this user's name
            '-M',  # Don't create a home directory
            '-s', self.dummy_shell,  # No shell access allowed
            OBSRVBL_USER
        ]
        call(args)


# Specific release classes

class RaspbianWheezyUpstart(UpstartMixin, DebianMixin, BaseSystem):
    """
    Supports the 2015-02-16 version of Raspbian (based on Debian Wheezy)
    if and only if the `upstart` package is installed and has replaced
    SysVinit.
    """


class RHEL_5(SysVMixin, BaseSystem):
    """
    Supports Red Hat Enterprise Linux 5-compatible distributions, including
    CentOS 5 and Scientific Linux 5. Not compatible with later versions, which
    do not use SysV init.
    """
    def add_user(self):
        # Don't create a user that already exists
        if OBSRVBL_USER in self.get_users():
            return

        # Create the system group
        call(['groupadd', '-f', '-r', OBSRVBL_USER])

        args = [
            'useradd',
            '-g',  OBSRVBL_USER,  # Assign to the system group
            '-d',  OBSRVBL_ROOT,  # Assign a home directory
            '-r',  # System user
            '-s', '/sbin/nologin',  # No shell access allowed
            OBSRVBL_USER
        ]
        call(args)


class RHEL_6(UpstartMixin, RedHatMixin, BaseSystem):
    """
    Supports Red Hat Enterprise Linux 6-compatible distributions, including
    CentOS 6 and Scientific Linux 6. Not compatible with earlier or later
    versions, which do not use Upstart.
    """
    dummy_shell = '/bin/false'


class RHEL_7(SystemdMixin, RedHatMixin, BaseSystem):
    """
    Supports Red Hat Enterprise Linux 7-compatible distributions, including
    CentOS 7 and Scientific Linux 7. Not compatible with earlier versions,
    which do not use systemd.
    """
    systemd_service_dir = '/usr/lib/systemd/system'
    systemd_startup_dir = '/etc/systemd/system'


class SE2Linux(SystemdMixin, BusyBoxMixin, BaseSystem):
    """
    SE2Linux for embedded systems.
    """
    systemd_service_dir = '/usr/lib/systemd/system'
    systemd_startup_dir = '/etc/systemd/system'


class UbuntuPrecise(UpstartMixin, DebianMixin, BaseSystem):
    """
    Supports Ubuntu installations with the upstart init system, default
    from Precise (12.04) to Utopic (14.10).
    """


class UbuntuVivid(SystemdMixin, DebianMixin, BaseSystem):
    """
    Supports Ubuntu installations with the systemd init system, default
    from Vivid (15.04). systemd is optionally available in Utopic (14.10).
    """
    systemd_service_dir = '/lib/systemd/system'
    systemd_startup_dir = '/etc/systemd/system'
