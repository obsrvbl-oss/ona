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
from os import environ as os_environ
from json import dumps
from logging import getLogger, DEBUG, Formatter
from logging.handlers import SysLogHandler
from socket import gethostname, SOCK_DGRAM, SOCK_STREAM
from time import gmtime, sleep

# local
from ona_service.service import Service
from ona_service.snmp_handler import SnmpHandler, SNMP_TRAP_PORT, V2 as SNMPV2
from ona_service.utils import utc, utcnow, persistent_dict

logger = getLogger(__name__)

ENV_NOTIFICATION_TYPES = 'OBSRVBL_NOTIFICATION_TYPES'
DEFAULT_NOTIFICATION_TYPES = 'alerts observations'

POST_PUBLISH_WAIT_SECONDS = 0.020
UPDATE_INTERVAL_SECONDS = 60
STATE_FILE = '.notifications.state'
MESSAGE_MAP = {
    'alerts':  {'endpoint': 'alerts', 'priority': 'error'},
    'observations': {'endpoint': 'observations', 'priority': 'info'},
    'alerts-detail': {'endpoint': 'alert-notifications', 'priority': 'error'},
}

CONFIG_DEFAULTS = {
    'syslog_enabled': 'false',
    'syslog_facility': 'user',
    'syslog_format': ('{time} {sensor_hostname} OBSRVBL '
                      '[{facility}.{priority}] {message}'),
    'syslog_server': None,
    'syslog_server_port': 162,
    'syslog_server_protocol': 'udp',

    'snmp_enabled': 'false',
    'snmp_objectid': None,
    'snmp_server': None,
    'snmp_server_port': SNMP_TRAP_PORT,
    'snmp_user': None,
    'snmp_version': SNMPV2,
    'snmpv3_engineid': None,
    'snmpv3_passphrase': None,
}


# translate from human readable config key names to what's in the env
def cfg_format(key):
    return 'OBSRVBL_{}'.format(key.upper())


# application config
_CONFIG = {}


# how we actually read the config
def config(key):
    return _CONFIG[cfg_format(key)]


# how we reload the config
def _reload_config():
    global _CONFIG
    _CONFIG = {cfg_format(k): v for k, v in CONFIG_DEFAULTS.items()}
    _CONFIG.update(os_environ)


def create_logger():
    _reload_config()

    log = getLogger('obsrvbl')
    log.setLevel(DEBUG)
    log.propagate = False

    # set up handlers
    log.handlers = []
    if config('snmp_enabled').lower() == 'true':
        log.addHandler(_snmp_log_handler(config))
    if config('syslog_enabled').lower() == 'true':
        log.addHandler(_syslog_log_handler(config, gethostname()))

    return log


def _snmp_log_handler(config):
    snmp_config = {
        'host': config('snmp_server'),
        'port': int(config('snmp_server_port')),
        'objectID': config('snmp_objectid'),
        'user': config('snmp_user'),
        'version': config('snmp_version'),
        'engineID': config('snmpv3_engineid'),
        'passcode': config('snmpv3_passphrase'),
    }
    return SnmpHandler(**snmp_config)


def _syslog_log_handler(config, hostname):
    host = config('syslog_server')
    port = int(config('syslog_server_port'))

    if config('syslog_server_protocol').lower() == 'tcp':
        socktype = SOCK_STREAM
    else:
        socktype = SOCK_DGRAM

    log_format = config('syslog_format')
    facility = config('syslog_facility')

    handler = SysLogHandler(
        (host, port),
        SysLogHandler.facility_names[facility],
        socktype=socktype,
    )
    log_format = log_format.format(
        time='%(asctime)s.%(msecs)d+00:00',
        sensor_hostname=hostname,
        facility=facility,
        priority='%(levelname)s',
        message='%(message)s'
    )
    SYSLOG_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'
    handler.formatter = Formatter(log_format, datefmt=SYSLOG_DATE_FORMAT)
    handler.formatter.converter = gmtime  # UTC
    return handler


class NotificationPublisher(Service):
    """
    Routinely queries Observation infrastructure for new notification events.
    These are then forwarded to the configured syslog or snmp service.
    """
    def __init__(self, *args, **kwargs):
        kwargs.update({
            'poll_seconds': UPDATE_INTERVAL_SECONDS,
        })
        super().__init__(*args, **kwargs)
        self.state = persistent_dict(STATE_FILE)
        self.logger = create_logger()

        notification_types = os_environ.get(
            ENV_NOTIFICATION_TYPES, DEFAULT_NOTIFICATION_TYPES
        )
        self.notification_types = set(notification_types.split())

    def get_data(self, endpoint, params):
        try:
            result = self.api.get_data(endpoint, params).json()
        except ValueError:
            return None
        if 'error' in result:
            return None
        return result['objects']

    def _publish(self, message, priority):
        log_func = getattr(self.logger, priority)
        formatted = dumps(message)
        try:
            log_func(formatted)
        except Exception as ex:
            logger.warning(
                "Got error='%s' when trying to public "
                "priority='%s', message='%s'",
                ex,
                priority,
                message
            )
        else:
            logger.info(
                "Published message, priority='%s', message='%s'",
                priority,
                formatted
            )

    def publish(self, messages, priority):
        for m in messages:
            self._publish(m, priority)
            # Rest a bit before sending the next message
            sleep(POST_PUBLISH_WAIT_SECONDS)

    def execute(self, now=None):
        if not self.logger.handlers:
            return

        for data_type in self.notification_types:
            if data_type not in MESSAGE_MAP:
                continue

            endpoint = MESSAGE_MAP[data_type]['endpoint']
            priority = MESSAGE_MAP[data_type]['priority']

            try:
                params = self.state[data_type]
            except KeyError:
                params = {'time__gt': utcnow().replace(tzinfo=utc).isoformat()}
                self.state[data_type] = params

            messages = self.get_data(endpoint, params)
            if not messages:
                continue

            max_time = max(msg['time'] for msg in messages)
            self.state[data_type] = {'time__gt': max_time}
            self.publish(messages, priority)


if __name__ == '__main__':
    watcher = NotificationPublisher()
    watcher.run()
