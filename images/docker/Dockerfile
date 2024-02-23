FROM debian:11 AS ona

ARG APP_NAME=ona

ENV VIRTUAL_ENV "/root/.virtualenvs/$APP_NAME"
ENV PATH "$VIRTUAL_ENV/bin:$PATH"

SHELL ["/bin/bash", "-c"]

WORKDIR /obsrvbl

# Set locales - https://hub.docker.com/_/debian
RUN --mount=type=cache,target=/var/cache/apt apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install --quiet --assume-yes \
    locales \
    && rm -rf /var/lib/apt/lists/* \
	&& localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.utf8

# Install python3 and pip
RUN --mount=type=cache,target=/var/cache/apt apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install --quiet --assume-yes \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/var/cache/apt apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install --quiet --assume-yes \
    wget curl \
    nano \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Set python venv
RUN ln -s /usr/bin/python3 /usr/bin/python
RUN python -m venv $VIRTUAL_ENV

# Install python packages
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel ipython

# Install netsa-pkg
RUN curl -L -O https://assets-production.obsrvbl.com/ona-packages/netsa/v0.1.27/netsa-pkg.deb \
    && apt-get update && apt-get install --assume-yes --fix-missing ./netsa-pkg.deb \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf netsa-pkg.deb

# Use local copy of ONA service package if needed
# COPY ona-service_UbuntuXenialContainer_amd64.deb ./

# Install ONA service
RUN if [ ! -f ./ona-service_UbuntuXenialContainer_amd64.deb ] ;\
    then curl -L -O https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.2/ona-service_UbuntuXenialContainer_amd64.deb ;\
    else echo "Use cached package" ;fi \
    && apt-get update && apt-get install --assume-yes --fix-missing ./ona-service_UbuntuXenialContainer_amd64.deb \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ona-service_UbuntuXenialContainer_amd64.deb

# Switch to the unprivileged user, set some local configuration, and start.
COPY run.sh /opt/obsrvbl-ona/run.sh
RUN chmod +x /opt/obsrvbl-ona/run.sh

CMD ["/opt/obsrvbl-ona/run.sh"]