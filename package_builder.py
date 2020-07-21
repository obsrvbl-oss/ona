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

from argparse import ArgumentParser
from collections import namedtuple
from subprocess import check_call


SystemInfo = namedtuple('SystemInfo', 'package_type,dependencies')

REDHAT_COMMON = 'tcpdump',
RASBPI_COMMON = 'tcpdump', 'adduser'
UBUNTU_COMMON = 'tcpdump', 'adduser', 'python2.7', 'sudo'

SYSTEM_INFO = {
    'RHEL_6':
        SystemInfo('rpm', REDHAT_COMMON + ('python27',)),
    'RHEL_7':
        SystemInfo('rpm', REDHAT_COMMON + ('net-tools', 'python', 'sudo')),
    'RHEL_8':
        SystemInfo('rpm', REDHAT_COMMON + ('net-tools', 'python27', 'sudo')),
    'RaspbianJessie':
        SystemInfo('deb', RASBPI_COMMON),
    'UbuntuXenial':
        SystemInfo('deb', UBUNTU_COMMON + ('systemd-sysv', 'net-tools')),
    'UbuntuXenialContainer':
        SystemInfo('deb', UBUNTU_COMMON + ('net-tools',)),
}


def main(proc_arch, version, system_type):
    package_type = SYSTEM_INFO[system_type].package_type
    dependencies = SYSTEM_INFO[system_type].dependencies
    package_name = 'ona-service_{}_{}.{}'.format(
        system_type, proc_arch, package_type
    )
    postinst_script = 'postinst_{}.sh'.format(system_type)
    prerm_script = 'prerm.{}'.format(package_type)
    postrm_script = 'postrm.{}'.format(package_type)

    fpm_args = [
        'fpm',
        '-s', 'dir',
        '-t', package_type,
        '--name', 'ona-service',
        '--version', version,
        '--package', 'packaging/output/{}'.format(package_name),
        '--force',
        '--after-install', 'packaging/scripts/{}'.format(postinst_script),
        '--before-remove', 'packaging/scripts/{}'.format(prerm_script),
        '--after-remove', 'packaging/scripts/{}'.format(postrm_script),
        '--url', 'https://www.observable.net/',
        '--description', 'Observable Networks Sensor Appliance',
        '--maintainer',
        'Observable Networks, Inc. <engineering@observable.net>',
        '--license', 'Apache License 2.0',
        '--vendor', 'obsrvbl.com',
        '--architecture', proc_arch,
        '--config-files', '/opt/obsrvbl-ona/config.auto',
        '--config-files', '/opt/obsrvbl-ona/config.local',
    ]

    for d in dependencies:
        fpm_args.extend(['--depends', d])

    fpm_args.append('packaging/root/=/')

    check_call(fpm_args)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('proc_arch', help='Processor type')
    parser.add_argument('version', help='Version string')
    parser.add_argument('system_type', help='Name of Linux system',
                        choices=sorted(SYSTEM_INFO))
    args = parser.parse_args()
    main(args.proc_arch, args.version, args.system_type)
