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
import socket
from tempfile import NamedTemporaryFile
from time import sleep

# local
from service import Service

DATA_TYPE = 'hostnames'
UPDATE_INTERVAL_SECONDS = 600
HOSTNAME_RESOLUTION_INTERVAL_SECONDS = 0.1


def resolve_host_name(ip):
    """
    Resolve a single host name. Returns a string on success.
    If resolution fails, returns None.
    """
    host = None
    try:
        host = socket.gethostbyaddr(ip)[0]
    except socket.herror as e:
        logging.info('Failed to resolve "{}": {}'.format(ip, e))
    return host


def resolve_host_names(unresolved_ips):
    """
    for each ip, resolve its hostname. Don't overwhelm the router.
    Returns a dict of ip => hostname. Does not batch anything,
    this is a one-shot deal.
    """
    resolved_ips = dict()
    total = len(unresolved_ips)
    processed = 0

    for ip in unresolved_ips:
        resolved_ips[ip] = resolve_host_name(ip)
        processed += 1
        logging.info('Resolved "{}" to "{}" ({} of {}).'.format(
            ip, resolved_ips[ip], processed, total))
        sleep(HOSTNAME_RESOLUTION_INTERVAL_SECONDS)

    return resolved_ips


class HostnameResolver(Service):
    """
    Routinely queries Observable Networks for interesting IPs, fetches their
    hostnames, and pushes the results to the ON cloud.
    """
    def __init__(self, *args, **kwargs):
        kwargs.update({
            'poll_seconds': UPDATE_INTERVAL_SECONDS,
        })
        super(HostnameResolver, self).__init__(*args, **kwargs)

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
            data = {'path': path}
            self.api.send_signal(DATA_TYPE, data)

    def execute(self, now=None):
        ips = self._get_candidate_ips()
        if not ips:
            return
        resolved = resolve_host_names(ips)
        self._update_host_names(resolved, now)


if __name__ == '__main__':
    watcher = HostnameResolver()
    watcher.run()
