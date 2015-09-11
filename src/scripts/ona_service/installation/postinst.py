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

import system_tools


def main(system_type):
    """
    Carries out post-installation tasks; meant to run as root as part of
    package installation. `system_type` is the name of one of the classes
    defined in the system_tools module.
    """
    linux_system = getattr(system_tools, system_type)()

    try:
        linux_system.stop_service('obsrvbl-ona')
    except Exception:
        pass

    linux_system.add_user()
    linux_system.set_user_group()
    linux_system.set_owner()
    linux_system.set_sudoer()
    linux_system.install_services()

    try:
        linux_system.start_service('obsrvbl-ona')
    except Exception as e:
        print('Could not start obsrvbl-ona: {}'.format(e))


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument(
        'system_type',
        metavar='system_type',
        help='Name of Linux system class (e.g. UbuntuPrecise)'
    )
    args = parser.parse_args()
    main(args.system_type)
