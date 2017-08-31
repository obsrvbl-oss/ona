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
import glob
import logging
import os

from datetime import timedelta
from subprocess import check_call, check_output, CalledProcessError

# local
from service import Service
from utils import utcnow, utcoffset, get_ip

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

DATA_TYPE = 'logs'
UPDATE_INTERVAL_SECONDS = 600
MANAGE_SCRIPT = '/opt/suricata/manage.sh'
SURICATA_LOGDIR = '/opt/suricata/logs'
SURICATA_LOGNAME = 'eve.json'
SURICATA_RULE_PATH = '/opt/suricata/rules/downloaded.rules'


def _compress_log(file_path):
    try:
        check_call(['gzip', '-f', file_path])
    except CalledProcessError:
        logging.error('Could not compress %s', file_path)
    else:
        file_path = '{}.gz'.format(file_path)

    return file_path


def _signal_suricata(action):
    '''
    Calls out to the suricata-service's manage.sh script.
    '''
    try:
        check_output(['sudo', '-u', 'suricata', MANAGE_SCRIPT, action])
    except CalledProcessError as e:
        logging.error('Error with suricata manage script ({}), {}'.format(
            e.returncode, action))


class SuricataAlertWatcher(Service):
    def __init__(self, *args, **kwargs):
        kwargs.update({
            'poll_seconds': UPDATE_INTERVAL_SECONDS,
        })
        super(SuricataAlertWatcher, self).__init__(*args, **kwargs)
        self.log_dir = kwargs.get('log_dir', SURICATA_LOGDIR)
        self.log_type = 'suricata'

    def _rotate_logs(self):
        _signal_suricata('rotate-logs')

    def _upload(self, now, compress=False):
        '''
        Upload log files. Hopefully just one, but maybe the last one failed
        so we need to pick it up too...
        '''
        pattern = os.path.join(
            self.log_dir, '{}.*.archived'.format(SURICATA_LOGNAME)
        )
        for file_path in glob.iglob(pattern):
            if compress:
                file_path = _compress_log(file_path)
            path = self.api.send_file(DATA_TYPE, file_path, now,
                                      suffix=self.log_type)
            if path is not None:
                data = {
                    'path': path,
                    'log_type': self.log_type,
                    'utcoffset': utcoffset(),
                    'ip': get_ip(),
                }
                self.api.send_signal(DATA_TYPE, data)
            os.remove(file_path)

    def _update_rules(self):
        res = self.api.get_data('suricata-rules')
        with open(SURICATA_RULE_PATH, 'wb') as f:
            for chunk in res.iter_content(8192):
                f.write(chunk)
        _signal_suricata('reload-config')

    def execute(self, now=None):
        logging.info('Checking for Suricata alerts')
        self._rotate_logs()
        self._upload(now, compress=True)

        # ideally we'll update this to use the e-tag, for more responsive
        # config updates. But for now, do it at the start of every day.
        # we call utcnow() again to avoid the race condition where we miss
        # midnight.
        next_time = utcnow() + timedelta(seconds=UPDATE_INTERVAL_SECONDS)
        should_update = (now and next_time.date() > now.date())
        if (not os.path.exists(SURICATA_RULE_PATH)) or should_update:
            logging.info('Updating Suricata rules')
            self._update_rules()
            logging.info('Finished updating Suricata rules')


if __name__ == '__main__':
    watcher = SuricataAlertWatcher()
    watcher.run()
