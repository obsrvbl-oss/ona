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

. /opt/obsrvbl-ona/config
cd /opt/obsrvbl-ona/

# Poll the site for a configuration update. If one is found, the
# script will exit.
/usr/bin/python2.7 /opt/obsrvbl-ona/ona_service/ona.py

# Shut down all services to reload with a new environment.
/bin/kill -TERM `cat /tmp/ona-supervisord.pid`
sleep 5
