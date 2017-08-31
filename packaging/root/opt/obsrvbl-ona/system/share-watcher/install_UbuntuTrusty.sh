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

# Install Samba
apt-get update && apt-get install -y samba

# Create the shared directory
mkdir -p $OBSRVBL_SHARE_DIR
chown nobody:nogroup $OBSRVBL_SHARE_DIR
chmod 0777 $OBSRVBL_SHARE_DIR

# Configure Samba
cat << EOF > "/etc/samba/smb.conf"
[global]
	workgroup = $OBSRVBL_SHARE_WORKGROUP
	server string = %h server (Samba, Ubuntu)
	server role = standalone server
	map to guest = Bad User
	syslog = 0
	log file = /var/log/samba/log.%m
	max log size = 1000
	dns proxy = No
	usershare allow guests = Yes
	panic action = /usr/share/samba/panic-action %d
	idmap config * : backend = tdb
	vfs object = full_audit
	full_audit:prefix = %I|%m|%i
	full_audit:success = mkdir rmdir write pwrite rename unlink
	full_audit:failure = none
	full_audit:facility = local7
	full_audit:priority = alert

[guest]
	comment = Guest access
	path = $OBSRVBL_SHARE_DIR
	read only = No
	create mask = 0666
	guest ok = Yes
EOF

initctl restart smbd

# Configure iptables
iptables -A INPUT -p udp --dport 137 -m state --state NEW,ESTABLISHED -j ACCEPT
iptables -A INPUT -p udp --dport 138 -m state --state NEW,ESTABLISHED -j ACCEPT
iptables -A INPUT -p tcp --dport 139 -m state --state NEW,ESTABLISHED -j ACCEPT
iptables -A INPUT -p tcp --dport 445 -m state --state NEW,ESTABLISHED -j ACCEPT
iptables-save > /etc/iptables/rules.v4

# Configure RSYSLOG
cp /opt/obsrvbl-ona/system/share-watcher/rsyslog-config /etc/rsyslog.d/60-samba_audit.conf
touch /var/log/samba_audit.log
chown syslog:adm /var/log/samba_audit.log
chmod 0640 /var/log/samba_audit.log
initctl restart rsyslog

# Configure logrotate
cp /opt/obsrvbl-ona/system/share-watcher/logrotate-config /etc/logrotate.d/samba_audit

# Configure ona-service
echo 'OBSRVBL_SHARE_WATCHER="true"' >> /opt/obsrvbl-ona/config.local
chown obsrvbl_ona:obsrvbl_ona /opt/obsrvbl-ona/config.local
initctl restart obsrvbl-ona
