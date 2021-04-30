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
mkdir -p $PNA_LOGDIR

# Bring up the interface
/usr/bin/sudo /sbin/ifconfig $1 up promisc

# Generate the BPF filter
export OBSRVBL_BPF="`/usr/bin/python3 -c "print(' or '.join('(net {})'.format(x) for x in '$OBSRVBL_NETWORKS'.split()))"`"

# Run the monitor
exec /usr/bin/sudo \
    /opt/obsrvbl-ona/pna/user/pna \
        -i "$1" \
        -N "$OBSRVBL_NETWORKS" \
        -o "$PNA_LOGDIR" \
        -Z "obsrvbl_ona" \
        "$OBSRVBL_BPF"
