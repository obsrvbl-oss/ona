FROM debian:13 AS ona

ARG APP_NAME=ona
ARG ONA_PACKAGE_URL=https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.4/ona-service_DebianTrixieContainer_amd64.deb

ENV VIRTUAL_ENV="/root/.virtualenvs/$APP_NAME"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

SHELL ["/bin/bash", "-c"]

WORKDIR /obsrvbl

# Install system dependencies
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends --yes \
    build-essential \
    curl \
    locales \
    nano \
    python3.13 \
    python3-pip \
    python3.13-venv \
    vim \
    wget \
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.utf8

# Set python venv
RUN ln -s /usr/bin/python3.13 /usr/bin/python
RUN python -m venv "$VIRTUAL_ENV"

# Install python packages
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel ipython

# Install netsa-pkg
RUN curl -L -O https://assets-production.obsrvbl.com/ona-packages/netsa/v0.1.27/netsa-pkg.deb \
    && apt-get update && apt-get install --assume-yes --fix-missing ./netsa-pkg.deb \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf netsa-pkg.deb

# Install ONA service
RUN curl --fail --location \
    --output ona-service_DebianTrixieContainer_amd64.deb \
    "$ONA_PACKAGE_URL" \
    && apt-get update && apt-get install --assume-yes --fix-missing ./ona-service_DebianTrixieContainer_amd64.deb \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ona-service_DebianTrixieContainer_amd64.deb

# Switch to the unprivileged user, set some local configuration, and start.
COPY run.sh /opt/obsrvbl-ona/run.sh
RUN chmod +x /opt/obsrvbl-ona/run.sh

CMD ["/opt/obsrvbl-ona/run.sh"]
