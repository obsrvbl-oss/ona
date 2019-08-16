FROM ubuntu:18.04
LABEL maintainer="Observable Networks <support@obsrvbl.com>"

# Install dependencies.
RUN apt-get update && apt-get install -y --fix-missing adduser curl net-tools libglib2.0-0 liblzo2-2 libltdl7 libpcap0.8 python2.7 sudo tcpdump zlib1g

# Download and install the NetFlow receiver
RUN curl -L -O https://github.com/bbayles/netsa-pkg/releases/download/v0.1.12/netsa-pkg.deb
RUN dpkg -i netsa-pkg.deb

# Download and install ONA service
RUN curl -O https://s3.amazonaws.com/onstatic/ona/master/ona-service_UbuntuXenialContainer_amd64.deb
RUN dpkg -i ona-service_UbuntuXenialContainer_amd64.deb

# Switch to the unprivileged user, set some local configuration, and start.

COPY run.sh /opt/obsrvbl-ona/run.sh
RUN chmod +x /opt/obsrvbl-ona/run.sh

USER obsrvbl_ona

CMD ["/opt/obsrvbl-ona/run.sh"]
