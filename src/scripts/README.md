# Support scripts

Logging and daemonization is handled via the host O/S's standard mechanisms
(systemd/upstart/init). This means these scripts simply need to follow
standard conventions on signal processing and can be run manually via a
command-line invocation.
