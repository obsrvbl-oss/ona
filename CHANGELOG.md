# Change Log

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/).

## v1.0 - 2015-09-11

### Added

* Initial Release
* Services include:
  * obsrvbl-ona [default] - monitor for configuration changes, handle updates
    * All other services start with this service
  * log-watcher [default] - collect (relevant) sensor logs
  * pna-monitor [default] - collect IP traffic metadata
  * pna-pusher [default] - send metadata to the Observable cloud
  * pdns-capturer [default] - collect passive DNS queries
  * hostname-resolver [default] - resolve local IPs to hostnames for reference
  * netflow-monitor - act as a NetFlow collector
  * netflow-pusher - send netflow data to the Observable cloud
  * notification-publisher - relay Observable alerts and observations over
    syslog or SNMP
  * arp-capturer - collect ARP traffic from the LAN
  * ossec-alert-watcher - monitor OSSEC-based alerts (if installed)
  * suricata-alert-watcher - monitor Suricata-based alerts (if installed)
