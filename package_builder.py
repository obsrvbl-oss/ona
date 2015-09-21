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

SYSTEM_INFO = {
    'RaspbianWheezyUpstart': SystemInfo(
        'deb', ['adduser', 'tcpdump', 'upstart']
    ),
    'RHEL_5': SystemInfo(
        'rpm', []
    ),
    'RHEL_6': SystemInfo(
        'rpm', ['tcpdump']
    ),
    'RHEL_7': SystemInfo(
        'rpm', ['net-tools', 'python', 'sudo', 'tcpdump']
    ),
    'SE2Linux': SystemInfo(
        'rpm', ['tcpdump']
    ),
    'UbuntuPrecise': SystemInfo(
        'deb', ['adduser', 'python2.7', 'sudo', 'tcpdump']
    ),
    'UbuntuVivid': SystemInfo(
        'deb', ['adduser', 'python2.7', 'sudo', 'systemd-sysv', 'tcpdump']
    ),
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
    compression_flag = '--{}-compression'.format(package_type)

    fpm_args = [
        'fpm',
        '-s', 'dir',
        '-t', package_type,
        '-n', 'ona-service',
        '-v', version,
        '-p', 'packaging/output/{}'.format(package_name),
        '--force',
        '--after-install', 'packaging/scripts/{}'.format(postinst_script),
        '--before-remove', 'packaging/scripts/{}'.format(prerm_script),
        '--after-remove', 'packaging/scripts/{}'.format(postrm_script),
        '--url', 'https://www.observable.net/',
        '--description', 'Observable Networks Sensor Appliance',
        '-m', 'Observable Networks, Inc. <engineering@observable.net>',
        '--license', 'Apache License 2.0',
        '--vendor', 'obsrvbl.com',
        '-a', proc_arch,
        '--config-files', '/opt/obsrvbl-ona/config',
        compression_flag, 'bzip2',
    ]

    for d in dependencies:
        fpm_args.extend(['--depends', d])

    fpm_args.append('packaging/root/=/')

    check_call(fpm_args)

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('proc_arch', help='Processor type')
    parser.add_argument('version', help='Version string')
    parser.add_argument('system_type', help='Name of Linux system')
    args = parser.parse_args()
    main(args.proc_arch, args.version, args.system_type)
