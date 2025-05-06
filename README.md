# Observable Networks Appliance (ONA) #

This repository is where the development of the Observable Networks Appliance (ONA) takes place. The ONA software is used to collect input data for Observable Networks' network security service. It can run on a variety of platforms, including embedded computers, physical servers, virtual machines, cloud servers, and Docker containers.

## Download

### ISO (fully supported and recommended):

* [Ubuntu 24.04](https://assets-production.obsrvbl.com/ona-packages/iso/ona-24.04.1-v5.1.3-vmsetupfix/ona-24.04.1-server-amd64.iso)

### Package files for manual installation:

* [Ubuntu 24.04 and later](https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.3/ona-service_UbuntuNoble_amd64.deb)
* [RHEL 7 and compatible](https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.3/ona-service_RHEL_7_x86_64.rpm)
* [RHEL 8 and compatible](https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.3/ona-service_RHEL_8_x86_64.rpm)
* [Raspberry Pi with Raspbian (ARMHF)](https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.3/ona-service_RaspbianJessie_armhf.deb)
  ([installation guide](raspberry_pi_guide.md))
* [Raspberry Pi with Raspbian (ARM64)](https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.3/ona-service_RaspbianJessie_aarch64.deb)
  ([installation guide](raspberry_pi_guide.md))
* [Docker](https://github.com/obsrvbl/ona/blob/master/images/docker/Dockerfile)

To install the latest version on Ubuntu:

```
$ wget https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.3/ona-service_UbuntuNoble_amd64.deb
$ sudo apt install ./ona-service_UbuntuNoble_amd64.deb
```

To monitor NetFlow traffic, you'll also need to install tools from the [CERT NetSA Security Suite](https://tools.netsa.cert.org/):

```
$ wget https://assets-production.obsrvbl.com/ona-packages/netsa/v0.1.27/netsa-pkg.deb
$ sudo apt install ./netsa-pkg.deb
```

## Services

The ONA is composed of a number of configurable services, supervised by a single system service, `obsrvbl-ona`.
Control which services are running by editing `/opt/obsrvbl-ona/config.local`.
Some of the services include:

* __ONA Service__: Monitors for configuration updates
* __PNA Service__ - Collects and uploads IP traffic metadata from system network interfaces
* __IPFIX Capturer__ - Collects and uploads NetFlow, IPFIX, or sFlow data from remote exporters
* __Hostname Resolver__ - Resolve active IPs to local hostnames
* __Log watcher__: Monitors and uploads the sensor's authentication logs
* __PDNS Capturer__ - Collects and uploads passive DNS queries
