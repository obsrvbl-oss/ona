#!/bin/bash

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

# Install the ONA service package
dpkg -i /root/ona/ona-service.deb

# Set up firewall - relies on iptables-persistent package.
cp /root/ona/rules.v4 /etc/iptables/rules.v4
cp /root/ona/rules.v6 /etc/iptables/rules.v6

# Set a random hostname - assume's "ona-default" is current hostname.
rndstr="$(/usr/bin/mcookie | /usr/bin/cut -c -6)"
/bin/sed -i s/ona-default/ona-$rndstr/g /etc/host*

# Fix up MOTD.
for f in $(echo "10-help-text 50-landscape-sysinfo 90-updates-available 91-release-upgrade"); do
    rm /etc/update-motd.d/$f
done
cp /root/ona/motd.tail /etc/
