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

# python builtins
import json
import logging
import os
import socket
import subprocess
from tempfile import NamedTemporaryFile
from time import sleep

# local
from service import Service

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

DATA_TYPE = 'hostnames'
UPDATE_INTERVAL_SECONDS = 600
HOSTNAME_RESOLUTION_INTERVAL_SECONDS = 0.1
ENV_HOSTNAME_DNS = 'OBSRVBL_HOSTNAME_DNS'
ENV_HOSTNAME_NETBIOS = 'OBSRVBL_HOSTNAME_NETBIOS'


def gethostbyaddr(ip):
    """
    Resolve a single host name with gethostbyaddr. Returns a string on success.
    If resolution fails, returns None.
    """
    host = None
    try:
        host = socket.gethostbyaddr(ip)[0]
    except socket.error:
        pass
    return host


def nmblookup(ip, timeout_sec=1):
    """
    Resolve a single host name with nmblookup. Returns a string on success.
    If resolution fails, returns None.
    """
    host = None
    try:
        output = subprocess.check_output(
            ['timeout', '{}s'.format(timeout_sec), 'nmblookup', '-A', ip]
        )
    except subprocess.CalledProcessError:
        pass
    else:
        for line in output.splitlines():
            if '<GROUP>' in line:
                continue
            if ('<ACTIVE>' in line) and ('<00>' in line):
                fields = line.strip().split()
                host = fields[0].lower()
                break

    return host


def resolve_host_names(unresolved_ips, resolvers):
    """
    for each ip, resolve its hostname. Don't overwhelm the router.
    Returns a dict of ip => hostname. Does not batch anything,
    this is a one-shot deal.
    """
    ret = {}
    for ip in unresolved_ips:
        name = None
        for resolver in resolvers:
            name = resolver(ip)
            if name:
                break
        ret[ip] = name
        sleep(HOSTNAME_RESOLUTION_INTERVAL_SECONDS)

    return ret


class HostnameResolver(Service):
    """
    Routinely queries Observable Networks for interesting IPs, fetches their
    hostnames, and pushes the results to the ON cloud.
    """
    resolver_map = {'gethostbyaddr': gethostbyaddr, 'nmblookup': nmblookup}

    def __init__(self, *args, **kwargs):
        kwargs.update({
            'poll_seconds': UPDATE_INTERVAL_SECONDS,
        })
        super(HostnameResolver, self).__init__(*args, **kwargs)

        self.resolvers = []
        if os.environ.get(ENV_HOSTNAME_NETBIOS, 'false') == 'true':
            self.resolvers.append(nmblookup)
        if os.environ.get(ENV_HOSTNAME_DNS, 'true') == 'true':
            self.resolvers.append(gethostbyaddr)

    def _get_candidate_ips(self):
        try:
            result = self.api.get_data(DATA_TYPE).json()
        except ValueError:
            return None
        if 'error' in result:
            return None
        return result

    def _update_host_names(self, resolved, now):
        with NamedTemporaryFile() as f:
            f.write(json.dumps(resolved))
            f.seek(0)
            path = self.api.send_file(DATA_TYPE, f.name, now, suffix='hosts')
            if path is not None:
                data = {'path': path}
                self.api.send_signal(DATA_TYPE, data)

    def execute(self, now=None):
        if not self.resolvers:
            logging.error('No resolvers are set')

        ips = self._get_candidate_ips()
        if not ips:
            return
        resolved = resolve_host_names(ips, self.resolvers)
        self._update_host_names(resolved, now)


if __name__ == '__main__':
    watcher = HostnameResolver()
    watcher.run()
