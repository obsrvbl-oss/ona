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
from os.path import basename, join
from platform import node
from shutil import copy
from subprocess import call
from uuid import uuid4

OBSRVBL_ROOT = '/opt/obsrvbl-ona/'
OBSRVBL_USER = 'obsrvbl_ona'
OBSRVBL_SERVICE = 'obsrvbl-ona'
ONA_NAME_PREFIX = 'ona-'


class BaseSystem(object):
    logs_group = 'adm'
    admin_group = 'root'
    sudoers_path = '/etc/sudoers'

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
            ['chown', 'root:{}'.format(self.admin_group), pna_path],
        ):
            return_code = call(args)

            if return_code != 0:
                msg = 'Failed during: {}'.format(' '.join(args))
                raise RuntimeError(msg)

    def set_user_group(self):
        """
        Adds the ONA user to a group (adm or wheel) that lets it read the
        system logs.
        """
        call(['usermod', '-a', '-G', self.logs_group, OBSRVBL_USER])

    def set_sudoer(self):
        """
        Allows the ONA user to execute certain commands as root, sans password.
        Raises RuntimeError if something fails
        """
        sudoers_file_path = join(OBSRVBL_ROOT, 'system', 'obsrvbl_ona.sudoers')
        for args in (
            ['chown', 'root', sudoers_file_path],
            ['chmod', '0400', sudoers_file_path],
            ['cp', sudoers_file_path, '/etc/sudoers.d/obsrvbl_ona']
        ):
            return_code = call(args)
            if return_code != 0:
                raise RuntimeError('Failed during: {}'.format(' '.join(args)))

    def set_ona_name(self):
        """
        Write an identifier for the ONA to the local configuration file.
        """
        # If the hostname has already been set to something unqiue-ish
        # after the OS was installed, don't change anything.
        hostname = node()
        if hostname.startswith(ONA_NAME_PREFIX):
            return

        config_local_path = join(OBSRVBL_ROOT, 'config.local')

        # If the identifier has already been set by configuration, don't
        # change anything.
        with open(config_local_path, 'r') as infile:
            if any(line.startswith('OBSRVBL_ONA_NAME=') for line in infile):
                return

        # Otherwise, set a value to be used instead of the hostname.
        ona_name = ONA_NAME_PREFIX + uuid4().hex[:6]
        with open(config_local_path, 'a') as outfile:
            outfile.write('OBSRVBL_ONA_NAME="{}"\n'.format(ona_name))

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
        # Copy the ONA service file to the startup directory
        service_name = '{}.service'.format(OBSRVBL_SERVICE)
        src_path = join(OBSRVBL_ROOT, 'system/systemd', service_name)
        dst_path = join('/etc/systemd/system/', service_name)
        copy(src_path, dst_path)

        # Register the main ONA service
        call(['systemctl', 'daemon-reload'])
        call(['systemctl', 'enable', '{}.service'.format(OBSRVBL_SERVICE)])

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
        call(['addgroup', OBSRVBL_USER, self.logs_group])


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

class RaspbianJessie(SystemdMixin, DebianMixin, BaseSystem):
    """
    Supports the  2016-03-18 version of Raspbian (based on Debian Jessie).
    """


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


class SE2Linux(SystemdMixin, BusyBoxMixin, BaseSystem):
    """
    SE2Linux for embedded systems.
    """

    def set_sudoer(self):
        """
        Allows the ONA user to execute certain commands as root, sans password.
        This is crazy dangerous, so we use visudo to ensure that the changes we
        make are valid.
        """
        # Step 0: Check to see if the obsrvbl_ona entries are already present
        command = 'grep {} {} > /dev/null'.format(
            OBSRVBL_USER, self.sudoers_path
        )
        return_code = call([command], shell=True)
        if return_code == 0:
            print(
                '{} is already in {}'.format(OBSRVBL_USER, self.sudoers_path)
            )
            return

        # Step 1: Concatenate the original file and our additions to a
        # new file.
        # Step 2: Use visudo to check that the new file is valid.
        # Step 3: Verify that the new file is owned by the root user and group
        # Step 4: Set the new file's read/write/execute permissions to 0440
        # Step 5: Replace the original file
        src_path = join(OBSRVBL_ROOT, 'system', 'obsrvbl_ona.sudoers')
        tmp_path = join(OBSRVBL_ROOT, 'system', 'sudoers.tmp')
        for command in (
            'cat {} {} > {}'.format(self.sudoers_path, src_path, tmp_path),
            'visudo -c -f {}'.format(tmp_path),
            'chown root:{} {}'.format(self.admin_group, tmp_path),
            'chmod 0440 {}'.format(tmp_path),
            'mv {} {}'.format(tmp_path, self.sudoers_path),
        ):
            return_code = call([command], shell=True)

            if return_code != 0:
                print('Failed during: {}'.format(command))
                return


class UbuntuTrusty(UpstartMixin, DebianMixin, BaseSystem):
    """
    Supports Ubuntu installations with the upstart init system.
    """


class UbuntuXenial(SystemdMixin, DebianMixin, BaseSystem):
    """
    Supports Ubuntu installations with the systemd init system.
    """


class UbuntuXenialContainer(DebianMixin, BaseSystem):
    """
    Supports Ubuntu Xenial and above, but skips the systemd service steps.
    For use with Docker, etc.
    """
    def install_services(self):
        pass

    def start_service(self, service_name, instance=None):
        pass


class FreeBSD_10(BaseSystem):
    admin_group = 'wheel'
    sudoers_path = '/usr/local/etc/sudoers'

    def add_user(self):
        # Don't create a user that already exists
        if OBSRVBL_USER in self.get_users():
            return

        args = [
            'pw', 'useradd',
            '-n', OBSRVBL_USER,  # User name
            '-d', OBSRVBL_ROOT,  # Home directory
            '-s', '/sbin/nologin'  # No shell access allowed
        ]
        call(args)

    def install_services(self):
        src_path = join(
            OBSRVBL_ROOT, 'system/bsd-init/{}'.format(OBSRVBL_SERVICE)
        )
        dst_path = '/etc/rc.d/{}'.format(OBSRVBL_SERVICE)
        copy(src_path, dst_path)
        call(['chmod', '0555', dst_path])

    def set_user_group(self):
        pass

    def start_service(self, service_name, instance=None):
        return_code = call(['sudo', 'service', service_name, 'start'])

        if return_code != 0:
            err_msg = 'Error starting {}: {}'.format(service_name, return_code)
            raise RuntimeError(err_msg)

    def stop_service(self, service_name, instance=None):
        return_code = call(['sudo', 'service', service_name, 'stop'])

        return return_code
