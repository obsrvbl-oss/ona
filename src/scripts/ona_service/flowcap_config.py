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
import logging

from collections import defaultdict
from os import environ


FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

ENV_IPFIX_CONF = 'OBSRVBL_IPFIX_CONF'
DEFAULT_IPFIX_CONF = '/opt/obsrvbl-ona/ipfix/sensor.conf'

ENV_YAF_START_PORT = 'OBSRVBL_YAF_START_PORT'
DEFAULT_YAF_START_PORT = '4739'

PROBE_TYPES = {'netflow-v9', 'netflow-v5', 'ipfix', 'sflow'}


class FlowcapConfig(object):
    def __init__(self):
        self.ipfix_conf = environ.get(ENV_IPFIX_CONF, DEFAULT_IPFIX_CONF)
        self.probe_config = defaultdict(dict)

    def update(self):
        # Read per-probe settings from the environment
        for k, v in environ.iteritems():
            if not k.startswith('OBSRVBL_IPFIX_PROBE_'):
                continue

            parts = k.rsplit('_', 2)
            __, index, attr = parts

            try:
                int(index)
            except ValueError:
                logging.error('Probe index must be integer: %s', k)
                continue

            self.probe_config[index][attr] = v

        # YAF-specific probes
        if environ.get('OBSRVBL_YAF_CAPTURER', 'false') != 'true':
            return

        all_ifaces = sorted(environ.get('OBSRVBL_PNA_IFACES', '').split())
        yaf_start_port = int(
            environ.get(ENV_YAF_START_PORT, DEFAULT_YAF_START_PORT)
        )
        for i, iface in enumerate(all_ifaces):
            self.probe_config[iface]['TYPE'] = 'ipfix'
            self.probe_config[iface]['PORT'] = '{}'.format(yaf_start_port + i)
            self.probe_config[iface]['PROTOCOL'] = 'tcp'

    def write(self):
        with io.open(self.ipfix_conf, 'wt') as outfile:
            for index in sorted(self.probe_config):
                conf = self.probe_config[index]

                type_ = conf.get('TYPE')
                if type_ not in PROBE_TYPES:
                    logging.error('Unrecognized probe type: %s', type_)
                    continue

                try:
                    port = int(conf.get('PORT', '0'))
                except ValueError:
                    logging.error('Invalid port specified: %s', port)
                    continue
                if not (1024 <= port <= 65535):
                    logging.error('Port number out of range: %s', port)
                    continue

                protocol = conf.get('PROTOCOL', 'udp')
                if protocol not in {'tcp', 'udp'}:
                    logging.error('Invalid protocol: %s', protocol)
                    continue

                source = conf.get('SOURCE')
                if source == 'asa':
                    quirks = 'firewall-event zero-packets'
                else:
                    quirks = None

                id_ = 'S{}'.format(index) if index.isdigit() else index

                print('probe {} {}'.format(id_, type_), file=outfile)
                print('  listen-on-port {}'.format(port), file=outfile)
                print('  protocol {}'.format(protocol), file=outfile)
                if quirks:
                    print('  quirks {}'.format(quirks), file=outfile)
                print('end probe', file=outfile)
                print('', file=outfile)


if __name__ == '__main__':
    flowcap_config = FlowcapConfig()
    flowcap_config.update()
    flowcap_config.write()
