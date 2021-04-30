# Observable Networks Appliance (ONA) #

This repository is where the development of the Observable Networks Appliance (ONA) takes place. The ONA software is used to collect input data for Observable Networks' network security service. It can run on a variety of platforms, including embedded computers, physical servers, virtual machines, cloud servers, and Docker containers.

See [observable.net](https://observable.net) for more information about Observable Networks' network security service.

## Supported platforms

The following platforms are officially supported:

* [Ubuntu 18.04 and later](https://onstatic.s3.amazonaws.com/ona/master/ona-service_UbuntuXenial_amd64.deb)
* [RHEL 7 and compatible](https://onstatic.s3.amazonaws.com/ona/master/ona-service_RHEL_7_x86_64.rpm)
* [RHEL 8 and compatible](https://onstatic.s3.amazonaws.com/ona/master/ona-service_RHEL_8_x86_64.rpm)
* [Raspberry Pi with Raspbian](https://onstatic.s3.amazonaws.com/ona/master/ona-service_RaspbianJessie_armhf.deb)
* [Docker](https://github.com/obsrvbl/ona/blob/master/images/docker/Dockerfile)

To install the latest version on 20.04 (recommended for physical and virtual machine installations):

```
$ wget https://onstatic.s3.amazonaws.com/ona/master/ona-service_UbuntuXenial_amd64.deb
$ sudo apt install ./ona-service_UbuntuXenial_amd64.deb
```

To monitor NetFlow traffic, you'll also need to install tools from the [CERT NetSA Security Suite](https://tools.netsa.cert.org/):

```
$ wget http://onstatic.s3.amazonaws.com/netsa-pkg.deb
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
