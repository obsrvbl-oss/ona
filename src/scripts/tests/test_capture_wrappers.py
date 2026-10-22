#  Copyright 2026 Cisco Systems, Inc.
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
from os import environ, mkdir
from os.path import dirname, exists, join, normpath
from shutil import which
from subprocess import run
from tempfile import TemporaryDirectory
from unittest import TestCase

REPO_ROOT = normpath(join(dirname(__file__), '..', '..', '..'))
PACKAGE_ROOT = join(REPO_ROOT, 'packaging', 'root')
LIBEXEC_DIR = '/usr/libexec/obsrvbl-ona'
COMMON_PATH = join(
    PACKAGE_ROOT, 'usr', 'libexec', 'obsrvbl-ona', 'ona-capture-common.sh'
)
SUDOERS_PATH = join(
    PACKAGE_ROOT, 'opt', 'obsrvbl-ona', 'system', 'obsrvbl_ona.sudoers'
)
WRAPPERS = (
    'ona-capture-eta',
    'ona-capture-pdns',
    'ona-capture-pna',
    'ona-capture-yaf',
)

# dash is /bin/sh on the Debian and Raspbian packages, and the strictest
# shell the wrappers run under.
SHELL = which('dash') or '/bin/sh'
REJECTED = 64


class ShellCheckTestCase(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.net_dir = join(self.temp_dir.name, 'net')
        self.log_dir = join(self.temp_dir.name, 'logs')
        mkdir(self.net_dir)
        mkdir(self.log_dir)
        mkdir(join(self.net_dir, 'eth0'))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run(self, body, *args):
        # The library sets its directories unconditionally, so redirect them
        # after sourcing it.
        script = '. {} || exit 127\n'.format(COMMON_PATH)
        script += 'ONA_NET_DIR={}\n'.format(self.net_dir)
        script += 'ONA_LOG_DIR={}\n'.format(self.log_dir)
        script += body
        result = run(
            [SHELL, '-c', script, 'test-wrapper'] + list(args),
            capture_output=True,
            encoding='utf-8',
            env={'PATH': environ.get('PATH', '')},
        )
        self.assertNotEqual(result.returncode, 127, result.stderr)
        return result

    def _check(self, body, cases):
        # A positive control, so that a check rejecting everything cannot pass
        self.assertTrue(any(ok for _, ok in cases))
        self.assertTrue(any(not ok for _, ok in cases))

        for arg, ok in cases:
            with self.subTest(arg=arg):
                result = self._run(body, arg)
                expected = 0 if ok else REJECTED
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_require_iface(self):
        self._check('ona_require_iface "$1"', [
            ('eth0', True),
            ('eth1', False),
            ('', False),
            ('.', False),
            ('..', False),
            ('any', False),
            ('-i', False),
            ('eth0 -w /etc/shadow', False),
            ('../net/eth0', False),
            ('eth0;id', False),
        ])

    def test_require_capture_iface(self):
        self._check('ona_require_capture_iface "$1"', [
            ('eth0', True),
            ('any', True),
            ('eth1', False),
            ('-i', False),
        ])

    def test_require_integer(self):
        self._check('ona_require_integer "$1" 1024 65535', [
            ('1024', True),
            ('65535', True),
            ('1023', False),
            ('65536', False),
            ('', False),
            ('-1', False),
            ('01024', False),
            ('0x1283', False),
            ('4739 -z /tmp/evil', False),
            ('99999999999999999999', False),
        ])

    def test_require_network(self):
        self._check('ona_require_network "$1"', [
            ('10.0.0.0/8', True),
            ('2001:db8::/32', True),
            ('', False),
            ('-i', False),
            ('--plugin-name=/tmp/evil.so', False),
            ('10.0.0.0/8 -w /etc/shadow', False),
            ('$(id)', False),
        ])

    def test_require_log_dir(self):
        self._check('ona_require_log_dir "$1" pna', [
            (join(self.log_dir, 'pna'), True),
            (join(self.log_dir, 'pna') + '/', True),
            (join(self.log_dir, 'pdns'), False),
            (join(self.log_dir, 'pna', 'nested'), False),
            (join(self.log_dir, 'pdns', '..', 'pna'), False),
            ('/etc', False),
        ])

    def test_build_bpf(self):
        body = 'ona_build_bpf "$@"; printf "%s" "$ONA_BPF"'
        self.assertEqual(self._run(body).stdout, '')
        result = self._run(body, '10.0.0.0/8', '192.0.2.0/24')
        self.assertEqual(
            result.stdout, '(net 10.0.0.0/8) or (net 192.0.2.0/24)'
        )
        self.assertEqual(self._run(body, '10.0.0.0/8', '-i').returncode, 64)


class WrapperTestCase(TestCase):
    def test_shell_parses(self):
        for name in WRAPPERS + ('ona-capture-common.sh',):
            path = join(PACKAGE_ROOT, LIBEXEC_DIR.lstrip('/'), name)
            with self.subTest(name=name):
                self.assertTrue(exists(path))
                result = run([SHELL, '-n', path], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)


class SudoersTestCase(TestCase):
    def setUp(self):
        self.commands = set()
        with open(SUDOERS_PATH) as infile:
            for line in infile:
                if line.startswith('obsrvbl_ona ALL=(ALL) NOPASSWD:'):
                    self.commands.add(line.split()[3])

    def test_capture_commands_are_wrappers(self):
        wrappers = {join(LIBEXEC_DIR, x) for x in WRAPPERS}
        self.assertTrue(wrappers <= self.commands)

        # Granting any of these directly lets the caller choose root's argv
        for command in (
            '/sbin/ifconfig',
            '/usr/bin/tcpdump',
            '/opt/yaf/bin/yaf',
            '/opt/obsrvbl-ona/pna/user/pna',
            join(LIBEXEC_DIR, 'pna'),
        ):
            self.assertNotIn(command, self.commands)

    def test_nothing_runs_from_the_service_tree(self):
        # The service user owns /opt/obsrvbl-ona, so it can replace anything
        # in it.
        for command in self.commands:
            with self.subTest(command=command):
                self.assertFalse(command.startswith('/opt/obsrvbl-ona/'))
