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
import os

from datetime import datetime
from httplib import REQUEST_ENTITY_TOO_LARGE
from mock import patch, Mock
from tempfile import NamedTemporaryFile
from unittest import TestCase

from ona_service.api import (
    Api,
    ENV_OBSRVBL_SENSOR_EXT_ONLY,
    ENV_OBSRVBL_SERVICE_KEY,
    HTTP_TIMEOUT,
    requests,
    requests_exceptions,
    retry_connection,
)


class ApiTestCase(TestCase):
    def setUp(self):
        self.auth = ('service_key', 'my_key')
        os.environ[ENV_OBSRVBL_SERVICE_KEY] = self.auth[1]
        self.api = Api()
        self.api.ona_name = 'foo'

    def tearDown(self):
        del os.environ[ENV_OBSRVBL_SERVICE_KEY]

    def test_retry(self):
        exc = requests_exceptions.ConnectionError()
        self.assertTrue(retry_connection(exc))
        self.assertFalse(retry_connection(KeyError()))

    def _intercept_request(self, request, response):
        def closure(*args, **kwargs):
            file_data = kwargs.get('data')
            kwargs.update({
                'data': file_data.read(),
            })
            request(*args, **kwargs)
            return response
        return closure

    @patch('ona_service.api.requests', autospec=True)
    def test_send_file(self, mock_requests):
        # load the chamber
        mock_requests.get.return_value.json.return_value = {
            'headers': 'headers!',
            'url': 'url!',
            'method': 'SUPERGET',
            'path': 'remote_path!',
        }

        # some shenanigans to extort the data out of the open file handle.
        # see `mock_upload.assert_called_once_with` below.
        mock_upload = Mock()
        mock_upload_response = Mock()
        mock_requests.request.side_effect = self._intercept_request(
            mock_upload, mock_upload_response)

        # with everything set up, run the thing.
        time = datetime.utcnow()
        with NamedTemporaryFile() as f:
            f.write("hee hee hee")
            f.seek(0)
            remote_path = self.api.send_file('mytype', f.name, time)

        self.assertEquals(remote_path, 'remote_path!')

        file_url = '{base_url}/{YY}/{M}/{DD}/{T}/{name}'.format(
            base_url='https://sensor.ext.obsrvbl.com/sign/mytype',
            YY=time.year,
            M=time.month,
            DD=time.day,
            T=time.time(),
            name='foo',
        )
        mock_requests.get.assert_called_once_with(
            file_url,
            verify=True,
            timeout=HTTP_TIMEOUT,
            auth=self.auth,
            headers={}
        )
        mock_requests.get.return_value.raise_for_status.\
            assert_called_once_with()

        # mock_upload and mock_requests.request are the same call...
        mock_upload.assert_called_once_with(
            'SUPERGET', 'url!',
            headers='headers!', data='hee hee hee', verify=True,
            timeout=HTTP_TIMEOUT)
        self.assertEquals(mock_requests.request.call_count, 1)
        mock_upload_response.raise_for_status.assert_called_once_with()

    @patch('ona_service.api.requests', autospec=True)
    def test_send_file_suffix(self, mock_requests):
        mock_requests.get.return_value.json.return_value = {
            'headers': 'headers!',
            'url': 'url!',
            'method': 'SUPERGET',
            'path': 'remote_path!',
        }

        time = datetime.utcnow()
        with NamedTemporaryFile() as f:
            f.write("hee hee hee")
            f.seek(0)
            remote_path = self.api.send_file('mytype', f.name, time,
                                             suffix='mp3')

        self.assertEquals(remote_path, 'remote_path!')

        file_url = '{base_url}/{YY}/{M}/{DD}/{T}/{name}'.format(
            base_url='https://sensor.ext.obsrvbl.com/sign/mytype',
            YY=time.year,
            M=time.month,
            DD=time.day,
            T=time.time(),
            name='foo_mp3',
        )
        mock_requests.get.assert_called_once_with(
            file_url,
            verify=True,
            timeout=HTTP_TIMEOUT,
            auth=self.auth,
            headers={}
        )
        mock_requests.get.return_value.raise_for_status.\
            assert_called_once_with()

        self.assertEquals(mock_requests.request.call_count, 1)

    @patch('ona_service.api.requests', autospec=True)
    def test_send_file_fail(self, mock_requests):
        mock_requests.get.return_value.json.return_value = {
            'headers': 'headers!',
            'url': 'url!',
            'method': 'SUPERGET',
            'path': 'remote_path!',
        }
        response = requests.Response()
        response.status_code = REQUEST_ENTITY_TOO_LARGE
        mock_requests.request.return_value = response

        time = datetime.utcnow()
        with NamedTemporaryFile() as f:
            f.write("hee hee hee")
            f.seek(0)
            remote_path = self.api.send_file('mytype', f.name, time)

        self.assertIsNone(remote_path)

    @patch('ona_service.api.getenv', autospec=True)
    @patch('ona_service.api.requests', autospec=True)
    def test_send_file_headers(self, mock_requests, mock_getenv):
        # Ensure that the request gets sent with sensor_ext_only
        mock_requests.get.return_value.json.return_value = {
            'headers': 'headers!',
            'url': 'url!',
            'method': 'SUPERGET',
            'path': 'remote_path!',
        }
        response = requests.Response()
        response.status_code = REQUEST_ENTITY_TOO_LARGE
        mock_requests.request.return_value = response

        env_dict = {ENV_OBSRVBL_SENSOR_EXT_ONLY: 'true'}
        mock_getenv.side_effect = env_dict.get

        api = Api()

        time = datetime.utcnow()
        with NamedTemporaryFile() as f:
            f.write("hee hee hee")
            f.seek(0)
            api.send_file('mytype', f.name, time)

        self.assertEqual(
            mock_requests.get.call_args[1]['headers'],
            {'sensor-ext-only': 'true'}
        )

    @patch('ona_service.api.requests', autospec=True)
    def test_send_signal(self, mock_requests):
        data = {'some': 'data'}
        self.api.send_signal('mytype', data)

        mock_requests.post.assert_called_once_with(
            'https://sensor.ext.obsrvbl.com/signal/mytype/foo',
            verify=True,
            data=data,
            timeout=HTTP_TIMEOUT,
            auth=self.auth)

    @patch('ona_service.api.requests', autospec=True)
    def test_send_signal_empty(self, mock_requests):
        self.api.send_signal('mytype')

        mock_requests.post.assert_called_once_with(
            'https://sensor.ext.obsrvbl.com/signal/mytype/foo',
            verify=True,
            data=None,
            timeout=HTTP_TIMEOUT,
            auth=self.auth)

        response = mock_requests.post.return_value
        response.raise_for_status.assert_called_once_with()

    @patch('ona_service.api.requests', autospec=True)
    def test_get_data(self, mock_requests):
        # mock_response should be the return value of mock_requests.get()
        mock_response = self.api.get_data('mytype/myhost')

        mock_requests.get.assert_called_once_with(
            'https://sensor.ext.obsrvbl.com/get/mytype/myhost',
            params=None,
            verify=True,
            timeout=HTTP_TIMEOUT,
            auth=self.auth)
        mock_response.raise_for_status.assert_called_once_with()
