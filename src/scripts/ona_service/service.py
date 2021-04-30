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

from threading import Event
from time import sleep

# third-party
from requests import exceptions as requests_exceptions

# local
from ona_service.api import Api
from ona_service.utils import utcnow


FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT)


class Service:
    """
    Generic periodic service. Handles start/stop behavior, and scheduling of
    `execute()` every interval.

    Also holds an Api instance, because you might want one.
    """
    def __init__(self, *args, **kwargs):
        """
        Initialize the Service object.

        Keyword Arguments:
            poll_seconds: time between checks for new files
        """
        self.poll_seconds = kwargs.pop('poll_seconds')

        self.api = Api()
        self.stop_event = Event()

    def stop(self):
        self.stop_event.set()

    def execute(self, now=None):
        raise NotImplementedError()

    def run(self):
        while not self.stop_event.is_set():
            now = utcnow()
            try:
                self.execute(now=now)
            except requests_exceptions.RequestException as e:
                # catch any exception from the requests library
                logging.exception('persistent communication problem: %s', e)

            # Before we sleep, check if the stop_event is set
            if self.stop_event.is_set():
                break

            # now sleep for the service's interval
            time_taken = (utcnow() - now).total_seconds()
            delay_sec = max(0, self.poll_seconds - time_taken)
            sleep(delay_sec)

        logging.info('Service stopped')
