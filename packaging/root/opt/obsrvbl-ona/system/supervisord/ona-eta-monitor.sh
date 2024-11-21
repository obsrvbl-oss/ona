#!/bin/sh

#  Copyright 2018 Observable Networks
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

# Ensure log directory exists
mkdir -p $OBSRVBL_ETA_PCAP_DIR

# Wait until the next interval
sleep `expr $OBSRVBL_ETA_CAPTURE_SECONDS - \`date +%s\` % $OBSRVBL_ETA_CAPTURE_SECONDS`

# Run the monitor
exec /usr/bin/sudo \
    /usr/bin/tcpdump \
        -w "$OBSRVBL_ETA_PCAP_DIR/logs_%s.pcap" \
        -i "$OBSRVBL_ETA_CAPTURE_IFACE" \
        -s 0 \
        -C "$OBSRVBL_ETA_CAPTURE_MBITS" \
        -G "$OBSRVBL_ETA_CAPTURE_SECONDS" \
        -W "1" \
        -U \
        -Z "obsrvbl_ona" \
        "(udp dst port $OBSRVBL_ETA_UDP_PORT) and ((udp[8:2] == 9) or (udp[8:2] == 10))"
