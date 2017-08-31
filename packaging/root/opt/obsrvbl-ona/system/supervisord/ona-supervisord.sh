#!/bin/sh

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

# Set up the environment
cd /opt/obsrvbl-ona/
. /opt/obsrvbl-ona/config
export PYTHONPATH=/opt/obsrvbl-ona/ona_service/vendor

# Ensure the log directory exists
mkdir -p /opt/obsrvbl-ona/logs/ona_service

# Check in with the site for configuration updates
if [ -e /usr/bin/timeout ]; then
    /usr/bin/timeout 60s /usr/bin/python2.7 /opt/obsrvbl-ona/ona_service/ona.py --update-only
else
    /usr/bin/python2.7 /opt/obsrvbl-ona/ona_service/ona.py --update-only
fi

. /opt/obsrvbl-ona/config

# Set up supervisord's configuration file
/usr/bin/python2.7 /opt/obsrvbl-ona/ona_service/supervisor_config.py

# Run supervisord
exec /usr/bin/python2.7 \
    -m supervisor.supervisord \
    --nodaemon \
    -c /opt/obsrvbl-ona/system/supervisord/ona-supervisord.conf
