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

import io

from datetime import datetime
from os import environ
from os.path import join
from shutil import rmtree
from tempfile import mkdtemp
from unittest import TestCase

from mock import MagicMock

from ona_service.syslog_ad_watcher import SyslogADWatcher
from ona_service.utils import gunzip_bytes, utc

LOG_DATA_MULTILINE = (
    'obsrvbl_remote-ad|2016-05-21 06:49| May 21 06:49:34 2016\t4624\t'
    'Microsoft-Windows-Security-Auditing\t\tN/A\tAudit Success\t'
    'OBSRVBLDC1.obsrvbl.local\t12544\tAn account was successfully logged on.\n'
    'Subject:\n'
    '\tSecurity ID:\t\tS-1-0-0\n'
    '\tAccount Name:\t\t-\n'
    '\tAccount Domain:\t\t-\n'
    '\tLogon ID:\t\t0x0\n'
    'Logon Type:\t\t\t3\n'
    'Impersonation Level:\t\tImpersonation\n'
    'New Logon:\n'
    '\tSecurity ID:\t\tS-1-5-21-1979579619-958697405-47085797-1330\n'
    '\tAccount Name:\t\tACCOUNT241\n'
    '\tAccount Domain:\t\tOBSRVBL\n'
    '\tLogon ID:\t\t0x3E4614B3\n'
    '\tLogon GUID:\t\t{58534C60-0A0A-7CF7-F596-D9959A706044}\n'
    'Process Information:\n'
    '\tProcess ID:\t\t0x0\n'
    '\tProcess Name:\t\t-\n'
    'Network Information:\n'
    '\tWorkstation Name:\tCOMPUTER\n'
    '\tSource Network Address:\t192.168.0.100\n'
    '\tSource Port:\t\t64653\n'
    'Detailed Authentication Information:\n'
    '\tLogon Process:\t\tKerberos\n'
    '\tAuthentication Package:\tKerberos\n'
    '\tTransited Services:\t-\n'
    '\tPackage Name (NTLM only):\t-\n'
    '\tKey Length:\t\t0\n'
    'This event is generated when a logon session is created.\n'
)
LOG_DATA_ONELINE = (
    # Normal event
    'obsrvbl_remote-ad_oneline|2016-12-20 12:49| Dec 20 12:49:05 2016,4624,'
    'Microsoft-Windows-Security-Auditing,OBNET\\Account242,N/A,Success Audit,'
    'OBNETDC02.obsrvbl.local,Logon,,An account was successfully logged on.    '
    'Subject:   Security ID:  S-1-0-0   Account Name:  -   '
    'Account Domain:  -   Logon ID:  0x0    Logon Type:   3    '
    'Impersonation Level:  Delegation    New Logon:   '
    'Security ID:  S-1-5-21-1078081533-179605362-682003330-15279   '
    'Account Name:  Account242   Account Domain:  OBNET   '
    'Network Information:   Workstation Name:  WK242   '
    'Source Network Address: 192.0.2.2   Source Port:  52436    '
    '<truncated 2791 bytes>,1045983 \n'
    # Duplicate event
    'obsrvbl_remote-ad_oneline|2016-12-20 12:49| Dec 20 12:49:05 2016,4624,'
    'OBNETDC02.obsrvbl.local,Logon,,An account was successfully logged on.    '
    'Security ID:  S-1-5-21-1078081533-179605362-682003330-15279   '
    'Account Name:  Account242   Account Domain:  OBNET   '
    'Network Information:   Workstation Name:  WK242   '
    'Source Network Address: 192.0.2.2   Source Port:  52436    '
    '<truncated 2791 bytes>,1045983 \n'
    # Skipped SID
    'obsrvbl_remote-ad_oneline|2016-12-20 12:49| Dec 20 12:49:05 2016,4624,'
    'OBNETDC02.obsrvbl.local,Logon,,An account was successfully logged on.    '
    'Security ID:  S-1-5-18   '
    'Account Name:  FAKER   Account Domain:  OBNET   '
    'Network Information:   Workstation Name:  WK242   '
    'Source Network Address: 192.0.2.2   Source Port:  52436    '
    '<truncated 2791 bytes>,1045983 \n'
)


def _append_file(file_path, data):
    with io.open(file_path, 'ab') as outfile:
        print(data, file=outfile, end='')


class SyslogADWatcherTestCase(TestCase):
    def setUp(self):
        self.temp_dir = mkdtemp()
        self.log_path = join(self.temp_dir, 'remote-ad.log')
        self.now = datetime(2016, 5, 21, 13, 9, 30, tzinfo=utc)

        # Should be ignored by RemoteADLogNode
        _append_file(self.log_path, 'Bogus\n')

        environ['OBSRVBL_DOMAIN_SUFFIX'] = '.obsrvbl.local'
        environ['OBSRVBL_SYSLOG_AD_PATH'] = self.log_path
        self.inst = SyslogADWatcher(log_path=self.log_path)
        self.inst.api = MagicMock()
        self.inst.utcoffset = -(5 * 60 * 60)

    def tearDown(self):
        rmtree(self.temp_dir, ignore_errors=True)

    def test_execute_multiline(self):
        output = {}

        def send_file(data_type, path, now, suffix=None):
            with io.open(path, 'rb') as infile:
                output[index] = infile.read()

        self.inst.api.send_file.side_effect = send_file

        # There are two entries here, but we only know the first has ended once
        # we see the second.
        index = 0
        _append_file(self.log_path, LOG_DATA_MULTILINE)
        _append_file(self.log_path, LOG_DATA_MULTILINE)
        self.inst.execute(now=self.now)
        actual = gunzip_bytes(output[index]).splitlines()
        expected = [
            '_time,Computer,TargetUserName,EventCode,ComputerAddress',
            '1463831340,computer.obsrvbl.local,ACCOUNT241,4624,192.168.0.100',
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(self.inst.api.send_file.call_count, 1)
        self.assertEqual(self.inst.log_node.parsed_data, [])

        # No additional calls if there were no additional writes
        index = 1
        self.inst.execute(now=self.now)
        self.assertEqual(self.inst.api.send_file.call_count, 1)
        self.assertEqual(actual, expected)

        # Two more writes signal the end of the second and third entries, but
        # one is skipped
        index = 2
        _append_file(
            self.log_path, LOG_DATA_MULTILINE.replace('ACCOUNT241', 'USER$')
        )
        _append_file(self.log_path, LOG_DATA_MULTILINE)
        self.inst.execute(now=self.now)
        actual = gunzip_bytes(output[index]).splitlines()
        expected = [
            '_time,Computer,TargetUserName,EventCode,ComputerAddress',
            '1463831340,computer.obsrvbl.local,ACCOUNT241,4624,192.168.0.100',
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(self.inst.api.send_file.call_count, 2)

    def test_execute_oneline(self):
        output = {}

        def send_file(data_type, path, now, suffix=None):
            with io.open(path, 'rb') as infile:
                output[index] = infile.read()

        self.inst.api.send_file.side_effect = send_file

        index = 0
        _append_file(self.log_path, LOG_DATA_ONELINE)
        self.inst.execute(now=self.now)
        actual = gunzip_bytes(output[0]).splitlines()
        expected = [
            '_time,Computer,TargetUserName,EventCode,ComputerAddress',
            '1482256140,wk242.obsrvbl.local,Account242,4624,192.0.2.2',
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(self.inst.api.send_file.call_count, 1)
        self.assertEqual(self.inst.log_node.parsed_data, [])

        # No additional calls if there were no additional writes
        self.inst.execute(now=self.now)
        self.assertEqual(self.inst.api.send_file.call_count, 1)
