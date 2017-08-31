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

# Ensure log directory exists
mkdir -p $OBSRVBL_PDNS_PCAP_DIR

# Wait until the next interval
sleep `expr $OBSRVBL_PDNS_CAPTURE_SECONDS - \`date +%s\` % $OBSRVBL_PDNS_CAPTURE_SECONDS`

# Run the monitor
exec /usr/bin/sudo \
    /usr/sbin/tcpdump \
        -w "$OBSRVBL_PDNS_PCAP_DIR/pdns_%s.pcap" \
        -i "$OBSRVBL_PDNS_CAPTURE_IFACE" \
        -s 0 \
        -c `expr $OBSRVBL_PDNS_CAPTURE_SECONDS \* $OBSRVBL_PDNS_PPS_LIMIT` \
        -G "$OBSRVBL_PDNS_CAPTURE_SECONDS" \
        -U \
        -Z "obsrvbl_ona" \
        "ip and udp src port 53"
