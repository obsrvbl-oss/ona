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
from vendor.libnmap.process import NmapProcess
from vendor.libnmap.parser import NmapParser, NmapParserException

# local
from service import Service
from utils import send_observations, utc

OBSERVATION_TYPE = 'scan_observation_v1'
SCAN_TARGETS = 'scan-config'
SCAN_INTERVAL_SECONDS = 60 * 60  # Hourly.
DEFAULT_NMAP_ARGS = ['nmap', '-oG', '-']
MAX_SIMULTANEOUS_TARGETS = 10


def _run_scan(ips, now):
    nmap = NmapProcess(ips)
    rc = nmap.run()
    if rc != 0:
        logging.error("nmap failed with error {}".format(rc))
        return

    try:
        report = NmapParser.parse(nmap.stdout)
    except NmapParserException as e:
        logging.error("nmap parsing error? " + str(e))
        return

    ret = []
    for host in report.hosts:
        ports = ['{}/{}'.format(s.port, s.state) for s in host.services]
        obs = {
            'time': now.isoformat(),
            'source': host.address,
            'ports': ', '.join(ports),
            'info_type': 'services',
            'result': '',
        }
        ret.append(obs)

    return ret


class NmapperService(Service):
    def __init__(self, *args, **kwargs):
        kwargs.update({
            'poll_seconds': SCAN_INTERVAL_SECONDS,
        })
        super(NmapperService, self).__init__(*args, **kwargs)

    def _get_target_ips(self):
        json_resp = self.api.get_data(SCAN_TARGETS).json()
        objects = json_resp.get('objects', [])
        if not objects:
            return []

        is_enabled = objects[0].get('is_enabled', True)
        if not is_enabled:
            return []

        target_ips = objects[0].get('scan_targets', [])
        return target_ips

    def execute(self, now=None):
        logging.info('getting target ips')
        target_ips = self._get_target_ips()
        logging.info('got {} target ips'.format(len(target_ips)))

        # timezoneify now
        if now:
            now = now.replace(tzinfo=utc)

        while target_ips:
            ips = target_ips[0:MAX_SIMULTANEOUS_TARGETS]
            target_ips = target_ips[MAX_SIMULTANEOUS_TARGETS:]

            obs_data = _run_scan(ips, now)
            if not obs_data:
                continue

            send_observations(
                api=self.api,
                obs_type=OBSERVATION_TYPE,
                obs_data=obs_data,
                now=now,
                suffix='nmap',
            )


if __name__ == '__main__':
    scanner = NmapperService()
    scanner.run()
