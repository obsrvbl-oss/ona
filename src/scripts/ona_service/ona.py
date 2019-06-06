#!/usr/bin/env python

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

"""
This is the ONA update service. It is able to manage the local configuration
values set through the website.  `OBSRVBL_MANAGE_MODE` must be set to "auto"
in /opt/obsrvbl-ona/config for site configuration to apply.

Goals here are:
* report current version(s) of software to the site
* load known configuration values into a shell script for sourcing at start
* if any changes from the last check, signal that we need to restart service(s)
  and apply the change.
"""
from __future__ import print_function

import logging
import re

from argparse import ArgumentParser
from datetime import datetime
from errno import EAGAIN
from os import environ, listdir
from platform import platform, python_version
from sys import exit

from service import Service
from utils import utc, validate_pna_networks

# Logging configuration
FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

CHECK_INTERVAL = 60

AUTO_CONFIG_FILE = '/opt/obsrvbl-ona/config.auto'

# this defines a set of safe config params for use to export to the
# environment; we'll sanitize them, and the site should also sanitize them as
# well. They should be simple. The lower case character are UPPER case when
# exported.
CONFIG_WHITELIST = {
    # Parameters available on the site
    'HOST',
    'networks',
    'pdns_pps_limit',
    'syslog_enabled',
    'syslog_facility',
    'syslog_server',
    'syslog_server_port',
    'snmp_enabled',
    'snmp_objectid',
    'snmp_server',
    'snmp_server_port',
    'snmp_user',
    'snmp_version',
    'snmpv3_engineid',
    'snmpv3_passphrase',
    'snmpv3_passphrase',
    'ipfix_replace_timestamps',
    'ipfix_reverse_directions',
    'ETA_CAPTURE_MBITS',
    'ETA_UDP_PORT',
    # ONA services
    'PNA_SERVICE',
    'LOG_WATCHER',
    'HOSTNAME_RESOLVER',
    'NOTIFICATION_PUBLISHER',
    'BRO_LOG_WATCHER',
    'PDNS_CAPTURER',
    'SERVICE_OSSEC',
    'SERVICE_SURICATA',
    'IPFIX_CAPTURER',
    'KUBERNETES_WATCHER',
    'ETA_CAPTURER',
    # Other parameters
    'SERVICE_KEY',
    'PNA_IFACES',
    'PDNS_CAPTURE_IFACE',
    'BRO_LOG_PATH',
    'HOSTNAME_DNS',
    'HOSTNAME_NETBIOS',
    'SENSOR_EXT_ONLY',
}

IPFIX_PREFIX = 'IPFIX_PROBE_'
IPFIX_SUFFIXES = {'TYPE', 'PORT', 'PROTOCOL', 'SOURCE'}

ALLOWED_CHARS = re.compile(r"\A([-_*+.,:;<=>@'^?\n\r \tA-Za-z0-9])+\Z")


class ONA(Service):
    def __init__(self, *args, **kwargs):
        logging.info('Observable ONA service starting')
        self.config_file = kwargs.pop('config_file', AUTO_CONFIG_FILE)
        self.config_mode = environ.get('OBSRVBL_MANAGE_MODE', 'manual')
        self.update_only = kwargs.pop('update_only', False)
        self.current_config = self._load_config()

        self.network_ifaces = None
        if environ.get('OBSRVBL_WATCH_IFACES', 'false') == 'true':
            self.network_ifaces = self._get_network_ifaces()

        super(ONA, self).__init__(*args, **kwargs)

    def _report_to_site(self, now=None):
        """
        Sends data to the site about the state of this sensor and its software
        """
        now = now or datetime.now(utc)
        try:
            with open('/opt/obsrvbl-ona/version') as f:
                version = f.read().strip()
        except IOError:
            version = 'unknown'
        data = {
            'last_start': now.isoformat(),
            'platform': platform(),
            'python_version': python_version(),
            'ona_version': version,
            'config_mode': self.config_mode,
        }
        self.api.send_signal('sensors', data=data)

    def _retrieve_from_site(self):
        """
        Downloads configuration data from the site and returns it
        """
        # Check for configuration parameters. If we got some, normalize them.
        endpoint = 'sensors/{}'.format(self.api.ona_name)
        try:
            data = self.api.get_data(endpoint).json()
        except Exception:
            return

        config_dict = data.get('config') or {}
        site_config = self._build_config(config_dict)
        return site_config

    def _get_network_ifaces(self):
        return set(listdir('/sys/class/net/'))

    def _load_config(self):
        """
        Reads configuration from the local file, if it's available
        """
        try:
            with open(self.config_file) as fd:
                return fd.read().strip()
        except IOError:
            pass
        return ''

    def _write_config(self, config):
        """
        Writes `config` to the local file
        """
        with open(self.config_file, 'w') as fd:
            fd.write(config)

    def _build_config(self, config):
        # build the config based on the JSON provided config and the known
        # CONFIG_WHITELIST. Output should match the file we generate.
        if not config:
            return ''

        # Filter out None
        items = ((k, v) for k, v in config.iteritems() if v is not None)

        _config = []
        for key, value in items:
            # Check for values that match the IPFIX template or the whitelist
            upper_key = key.upper()
            if upper_key.startswith(IPFIX_PREFIX):
                suffix = upper_key.rsplit('_', 1)
                if (len(suffix) != 2) or (suffix[1] not in IPFIX_SUFFIXES):
                    continue
            elif key not in CONFIG_WHITELIST:
                continue

            # Convert all values to strings, making sure truth values are lower
            # case
            if (value is True) or (value is False):
                value = str(value).lower()
            else:
                value = str(value)

            # Validate CIDR addresses that are passed in, and ensure that all
            # other configuration values don't contain illegal characters
            if upper_key == 'NETWORKS':
                value = validate_pna_networks(value)
            elif ALLOWED_CHARS.match(value) is None:
                continue

            # Set the remote server
            if upper_key == 'HOST':
                value = 'https://{}'.format(value)

            _config.append('OBSRVBL_{}="{}"'.format(upper_key, value))

        return '\n'.join(sorted(_config))

    def execute(self, now=None):
        should_reload = False

        # Retrieve configuration from the site if we're in automatic mode
        if self.config_mode == 'auto':
            site_config = self._retrieve_from_site()
            if site_config and (site_config != self.current_config):
                logging.info('Configuration updated, reloading')
                self._write_config(site_config)
                should_reload = True

        # Check for network interface changes if we're monitoring those
        if self.network_ifaces is not None:
            if self.network_ifaces != self._get_network_ifaces():
                logging.info('Network interfaces changed')
                should_reload = True

        # For an --update-only run, report stats and prepare to exit naturally
        # if there were no configuration changes
        if self.update_only:
            self._report_to_site(now=now)
            self.stop()

        # If there were configuration changes, exit more abruptly.
        # We should be resurrected by the init system.
        if should_reload:
            exit(EAGAIN)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--config-file', help='Location of configuration file')
    parser.add_argument(
        '--update-only',
        action='store_true',
        help='Checks for new configuration from the site and then stops'
    )
    args = parser.parse_args()

    ona = ONA(
        poll_seconds=CHECK_INTERVAL,
        update_only=args.update_only
    )
    ona.run()
