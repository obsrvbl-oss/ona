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
from collections import namedtuple

import io
import logging

from collections import defaultdict
from distutils.spawn import find_executable
from os import environ
from subprocess import call, CalledProcessError, check_output, STDOUT


FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

ENV_IPFIX_CONF = 'OBSRVBL_IPFIX_CONF'
DEFAULT_IPFIX_CONF = '/opt/obsrvbl-ona/ipfix/sensor.conf'

ENV_YAF_START_PORT = 'OBSRVBL_YAF_START_PORT'
DEFAULT_YAF_START_PORT = '4739'

ENV_IPSET_UDP_CONF = 'OBSRVBL_IPSET_UDP_CONF'
DEFAULT_IPSET_UDP_CONF = '/opt/obsrvbl-ona/system/netflow-udp.ipset'

ENV_IPSET_TCP_CONF = 'OBSRVBL_IPSET_TCP_CONF'
DEFAULT_IPSET_TCP_CONF = '/opt/obsrvbl-ona/system/netflow-tcp.ipset'

IPSET_PATH = find_executable('ipset') or '/sbin/ipset'
IPTABLES_PATH = find_executable('iptables') or '/sbin/iptables'

PROBE_TYPES = {'netflow-v9', 'netflow-v5', 'ipfix', 'sflow'}

ProbeItem = namedtuple(
    'ProbeItem', ['index', 'type_', 'port', 'protocol', 'source', 'local']
)


class FlowcapConfig(object):
    def __init__(self):
        self.ipfix_conf = environ.get(ENV_IPFIX_CONF, DEFAULT_IPFIX_CONF)
        self.ipset_udp_conf = environ.get(
            ENV_IPSET_UDP_CONF, DEFAULT_IPSET_UDP_CONF
        )
        self.ipset_tcp_conf = environ.get(
            ENV_IPSET_TCP_CONF, DEFAULT_IPSET_TCP_CONF
        )
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
            self.probe_config[iface]['localhost_only'] = True

    def valid_probes(self):
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

            local = conf.get('localhost_only', False)

            yield ProbeItem(index, type_, port, protocol, source, local)

    def get_sensor_conf(self):
        added = set()

        with io.StringIO() as outfile:
            valid_probes = self.valid_probes()
            for index, type_, port, protocol, source, local in valid_probes:
                # Prevent duplicates from being written
                port_protocol = port, protocol
                if port_protocol in added:
                    logging.warning(
                        'Duplicate configuration detected for %s/%s',
                        port,
                        protocol
                    )
                    continue
                added.add(port_protocol)

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

            return outfile.getvalue()

    def write(self):
        with io.open(self.ipfix_conf, 'wt') as outfile:
            outfile.write(self.get_sensor_conf())

    def _should_add(self, rule_args):
        check_args = ['sudo', '-n', IPTABLES_PATH, '-C']
        # Check for the existence of the rule
        try:
            check_output(check_args + rule_args, stderr=STDOUT)
        # If we get an error saying it doesn't exist, we can add it
        except CalledProcessError as e:
            if (e.returncode == 1) and ('iptables: Bad rule' in e.output):
                return True
        # If we get some other error, we shouldn't add it
        except Exception:
            pass
        # If we didn't get an error, the rule exists and we shouldn't add it
        else:
            pass

        return False

    def configure_iptables(self):
        nonlocal_probes = [x for x in self.valid_probes() if not x.local]
        udp_ports = [x.port for x in nonlocal_probes if x.protocol == 'udp']
        tcp_ports = [x.port for x in nonlocal_probes if x.protocol == 'tcp']

        for protocol, ports, file_path in [
            ('udp', udp_ports, self.ipset_udp_conf),
            ('tcp', tcp_ports, self.ipset_tcp_conf),
        ]:
            set_name = 'netflow-{}'.format(protocol)

            # Write out the rules
            with io.open(file_path, 'wt') as outfile:
                line = 'create {} bitmap:port range 1024-65535'.format(
                    set_name
                )
                print(line, file=outfile)
                for port in ports:
                    line = 'add {} {}'.format(set_name, port)
                    print(line, file=outfile)

            # Restore the ipset configuration
            ipset_args = [
                'sudo', '-n',
                IPSET_PATH, 'restore',
                '-exist',
                '-file', file_path
            ]
            ipset_return = call(ipset_args)
            if ipset_return:
                logging.warning('could not restore rules')

            # Construct a rule
            rule_args = [
                'INPUT',
                '-p', protocol,
                '-m', 'set',
                '--match-set', set_name, 'dst',
                '-j', 'ACCEPT'
            ]

            # Check for an existing rule
            if not self._should_add(rule_args):
                logging.info('skipping firewall rule for %s', set_name)
                continue

            # Add the rule
            add_args = ['sudo', '-n', IPTABLES_PATH, '-A']
            iptables_return = call(add_args + rule_args)
            if iptables_return:
                logging.warning('could not update the firewall')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-w',
        '--write',
        action='store_true',
        help='Write the sensor.conf file'
    )
    parser.add_argument(
        '-f',
        '--firewall',
        action='store_true',
        help='Update the host firewall'
    )
    args = parser.parse_args()

    flowcap_config = FlowcapConfig()
    flowcap_config.update()

    print(flowcap_config.get_sensor_conf())

    if args.write:
        flowcap_config.write()

    if args.firewall:
        flowcap_config.configure_iptables()
