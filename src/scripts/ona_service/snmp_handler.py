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
# python builtins
import logging
import os
import subprocess

SNMP_TRAP_PORT = 162
V2 = '2c'
V3 = '3'


class SnmpHandler(logging.Handler):
    """
    A log handler class for parsing/emitting messages as SNMP traps.

    Only sends messages of type 'ERROR' at present. That is, he only sends
    alerts.
    """

    def __init__(self, user, objectID, version=V2, host='localhost',
                 port=SNMP_TRAP_PORT, passcode=None, engineID=None,
                 authentication='SHA'):
        """
        Initialize a handler.

        *** used for both v2c and v3 ***
        host: snmp server
        port: snmp server port. Default is 162.
        user: v2: snmp -c [community]
              v3: snmp -u [user]
        objectID: message type code, more or less. ASN.1 format.

        *** v3-only args ***
        engineID: prefixed with 0x on the command line, this is a
                  per-environment configuration setting.
        passcode: snmp -A [passcode]
        authentication: hash function for authentication. Options are SHA1 and
                        MD5.
        """
        super().__init__()

        self.host = host
        self.port = port
        self.formatter = None

        self.user = user
        self.version = version
        self.objectID = objectID
        self.passcode = passcode
        self.engineID = engineID
        self.authentication = authentication

    def _auth_args(self):
        if self.version == V3:
            return [
                "-e", "0x" + self.engineID,
                "-u", self.user,
                "-a", self.authentication,
                "-x", "AES",  # because ... DES? seriously?
                "-A", self.passcode,
                "-l", "authNoPriv",
            ]
        else:  # V2
            return ["-c", self.user]

    def _command_args(self, msg):
        args = [
            "snmptrap",
            "-v", self.version,
        ]
        args += self._auth_args()
        args += [
            "{}:{}".format(self.host, self.port),
            "''",  # this is so snmptrap reports the correct uptime. FYI.
            ".{}".format(self.objectID),
            ".{}.0".format(self.objectID),
            "s", "'{}'".format(msg),
        ]
        return args

    def emit(self, record):
        """
        Emit a record.

        If the record matches our requirements, it is formatted and sent
        to the snmp server.
        """
        if record.levelname != 'ERROR':
            return
        msg = self.format(record)
        with open(os.devnull, 'w') as FNULL:
            subprocess.call(self._command_args(msg),
                            stdout=FNULL, stderr=subprocess.STDOUT)
