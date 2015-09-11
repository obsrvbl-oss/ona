FROM ubuntu:14.04
MAINTAINER Observable Networks "support@obsrvbl.com"

# (Required) Replace this with your ONA service key
ENV ona_service_key=""

# (Optional) Add or remove local subnets for monitoring.
# This is a space-delimited list of CIDR blocks in standard notation
# ENV monitor_subnets="10.0.0.0/8"
ENV monitor_subnets="10.0.0.0/8 172.16.0.0/12 192.168.0.0/16"

# (Optional) Configure syslog.
ENV syslog_enabled="true"
ENV syslog_facility="user"
ENV syslog_server="127.0.0.1"
ENV syslog_server_port="514"

# Install dependencies.
RUN apt-get update && apt-get install -y --fix-missing adduser curl python2.7 sudo tcpdump

# Download and install ONA service
RUN curl -O https://s3.amazonaws.com/onstatic/ona/master/ona-service_UbuntuPrecise_amd64.deb
RUN dpkg -i ona-service_UbuntuPrecise_amd64.deb

# Switch to the unprivileged user, set some local configuration, and start.
USER obsrvbl_ona
RUN echo "OBSRVBL_MANAGE_MODE='manual'" >> /opt/obsrvbl-ona/config.local
RUN echo "OBSRVBL_SERVICE_KEY='${ona_service_key}'" >> /opt/obsrvbl-ona/config.local
RUN echo "OBSRVBL_NETWORKS='${monitor_subnets}'" >> /opt/obsrvbl-ona/config.local
RUN echo "OBSRVBL_LOG_WATCHER='false'" >> /opt/obsrvbl-ona/config.local

RUN echo "OBSRVBL_SYSLOG_ENABLED='${syslog_enabled}'" >> /opt/obsrvbl-ona/config.local
RUN echo "OBSRVBL_SYSLOG_FACILITY='${syslog_facility}'" >> /opt/obsrvbl-ona/config.local
RUN echo "OBSRVBL_SYSLOG_SERVER='${syslog_server}'" >> /opt/obsrvbl-ona/config.local
RUN echo "OBSRVBL_SYSLOG_SERVER_PORT='${syslog_server_port}'" >> /opt/obsrvbl-ona/config.local

CMD ["/opt/obsrvbl-ona/system/supervisord/ona-supervisord.sh"]
