#!/bin/sh -ex

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

mkdir -p "$OBSRVBL_IPFIX_LOGDIR"

ROTATE_PERIOD=60

export TZ="Etc/UTC"
export SILK_LIBFIXBUF_SUPPRESS_WARNINGS="1"

# Write the configuration file
/usr/bin/python2.7 /opt/obsrvbl-ona/ona_service/flowcap_config.py

exec /opt/silk/sbin/flowcap \
    --destination-directory="$OBSRVBL_IPFIX_LOGDIR" \
    --sensor-configuration="$OBSRVBL_IPFIX_CONF" \
    --max-file-size="104857600" \
    --timeout="$ROTATE_PERIOD" \
    --clock-time="$ROTATE_PERIOD" \
    --compression-method="none" \
    --log-destination="stdout" \
    --log-level="warning" \
    --no-daemon
