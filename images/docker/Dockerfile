FROM ubuntu:18.04
LABEL maintainer="Observable Networks <support@obsrvbl.com>"

# Install dependencies.
RUN apt-get update && apt-get install -y curl

RUN curl -L -O https://assets-production.obsrvbl.com/ona-packages/netsa/v0.1.27/netsa-pkg.deb
RUN curl -L -O https://s3.amazonaws.com/onstatic/ona/master/ona-service_UbuntuXenialContainer_amd64.deb
RUN apt install -y --fix-missing ./netsa-pkg.deb ./ona-service_UbuntuXenialContainer_amd64.deb

# Switch to the unprivileged user, set some local configuration, and start.
COPY run.sh /opt/obsrvbl-ona/run.sh
RUN chmod +x /opt/obsrvbl-ona/run.sh

USER obsrvbl_ona

CMD ["/opt/obsrvbl-ona/run.sh"]
