FROM ubuntu:14.04
MAINTAINER Observable Networks "support@obsrvbl.com"

# Install dependencies.
RUN apt-get update && apt-get install -y --fix-missing adduser curl python2.7 sudo tcpdump

# Download and install ONA service
RUN curl -O https://s3.amazonaws.com/onstatic/ona/master/ona-service_UbuntuPrecise_amd64.deb
RUN dpkg -i ona-service_UbuntuPrecise_amd64.deb

# Switch to the unprivileged user, set some local configuration, and start.

COPY images/docker/run.sh /opt/obsrvbl-ona/run.sh
RUN chmod +x /opt/obsrvbl-ona/run.sh

USER obsrvbl_ona

CMD ["/opt/obsrvbl-ona/run.sh"]
