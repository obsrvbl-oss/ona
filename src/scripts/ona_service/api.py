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
import io
import logging
import platform

from httplib import REQUEST_ENTITY_TOO_LARGE
from os import getenv

# third-party
from vendor import requests
from vendor.requests import exceptions as requests_exceptions
from vendor.retrying import retry

# Logging setup: When using Python versions < 2.7.9, urllib3 raises
# InsecurePlatformWarning to note that certain features are unavailable.
# These should not be logged repeatedly.
logging.captureWarnings(True)
py_warnings_logger = logging.getLogger('py.warnings')
py_warnings_logger.setLevel(logging.ERROR)
urllib3_logger = logging.getLogger('vendor.requests.packages.urllib3')
urllib3_logger.setLevel(logging.ERROR)

# Requests setup: Wait HTTP_TIMEOUT seconds before timing out.
HTTP_TIMEOUT = 300.0

ENV_OBSRVBL_HOST = 'OBSRVBL_HOST'
DEFAULT_OBSRVBL_HOST = 'https://sensor.ext.obsrvbl.com'
ENV_OBSRVBL_SERVICE_KEY = 'OBSRVBL_SERVICE_KEY'
ENV_OBSRVBL_ONA_NAME = 'OBSRVBL_ONA_NAME'


# Retrying setup: Wait min(BACKOFF_FACTOR * (2 ** i), BACKOFF_MAX) msec between
# between retries, up to MAX_ATTEMPTS times. Only retry when retry_connection
# returns True.
MIN_WAIT_MSEC = 1000
MAX_WAIT_MSEC = 10000
MAX_ATTEMPTS = 30


def retry_connection(exception):
    if isinstance(exception, requests_exceptions.RequestException):
        logging.warning('requests error: %s', exception)
        return True
    else:
        logging.exception('unknown error: %s', exception)
        return False


retry_kwargs = {
    'wait_random_min': MIN_WAIT_MSEC,
    'wait_random_max': MAX_WAIT_MSEC,
    'stop_max_attempt_number': MAX_ATTEMPTS,
    'retry_on_exception': retry_connection
}


class Api(object):
    """
    Handles communications with Observable Networks.
    Contains functions to send data, signal that data is ready for processing,
    and to retrieve data from the Observable cloud.
    """
    def __init__(self, *args, **kwargs):
        """
        Initialize the Api object.
        """
        self.proxy_uri = getenv(ENV_OBSRVBL_HOST, DEFAULT_OBSRVBL_HOST)
        self.request_args = {
            'verify': True,
            'timeout': HTTP_TIMEOUT,
        }
        # if they've set a service_key, grab it
        service_key = getenv(ENV_OBSRVBL_SERVICE_KEY, None)
        if service_key:
            self.request_args['auth'] = ('service_key', service_key)
        self.ona_name = getenv(ENV_OBSRVBL_ONA_NAME, platform.node())

    @retry(**retry_kwargs)
    def send_file(self, data_type, path, now, suffix=None):
        """
        Send a file to the ON service.

        Args:
            data_type: type of data that is being sent.
            path: local file path.
            now: the time period that corresponds to the file.
        """
        if suffix:
            name = '{}_{}'.format(self.ona_name, suffix)
        else:
            name = self.ona_name
        url = '{server}/sign/{type}/{year}/{month}/{day}/{time}/{name}'
        url = url.format(
            server=self.proxy_uri, type=data_type, year=now.year,
            month=now.month, day=now.day, time=now.time(),
            name=name)
        logging.info('Prepping file: {}'.format(url))
        response = requests.get(url, **self.request_args)
        response.raise_for_status()

        result = response.json()
        try:
            headers = result['headers']
            url = result['url']
            method = result['method']
            remote_path = result['path']
        except KeyError:
            raise requests_exceptions.RequestException(
                'Parameters missing from response'
            )

        with io.open(path, mode='rb') as data:
            logging.info('Sending file: {} {}'.format(method, url))
            resp = requests.request(
                method,
                url,
                headers=headers,
                data=data,
                verify=True,
                timeout=HTTP_TIMEOUT,
            )

        if resp.status_code == REQUEST_ENTITY_TOO_LARGE:
            logging.error('requests error: payload too large')
            return None

        resp.raise_for_status()
        return remote_path

    @retry(**retry_kwargs)
    def send_signal(self, data_type, data=None):
        """
        Send a signal to the ON service. Returns True on success.

        Args:
            data_type: type of signal to send
            data: a json value corresponding to the `data_type`.
        """
        url = '{server}/signal/{type}/{host}'
        url = url.format(
            server=self.proxy_uri, type=data_type, host=self.ona_name)
        logging.info('Sending process signal: {}:{}'.format(url, data))
        response = requests.post(url, data=data, **self.request_args)
        response.raise_for_status()
        logging.info('signal ok')

        return True

    @retry(**retry_kwargs)
    def get_data(self, data_url, params=None):
        """
        Retrieve data from the ON service.

        Args:
            data_url: resource we should fetch. This should be either
                `data_type`, or a "`data_type`/`ona_name`" string.
            params: optional query params to send

        Returns:
            Python-requests response. You can do things like r.json(), or
            r.text
        """
        url = '{server}/get/{type}'
        url = url.format(
            server=self.proxy_uri, type=data_url)
        logging.info('Downloading data: {}'.format(url))
        response = requests.get(url, params=params, **self.request_args)
        response.raise_for_status()
        return response
