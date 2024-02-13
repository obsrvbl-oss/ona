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
$ wget https://assets-production.obsrvbl.com/ona-packages/netsa/v0.1.27/netsa-pkg.deb
$ sudo apt install ./netsa-pkg.deb
```
### ONA Sensor with Raspberry PI
##### Requirements before start
- RaspberryPI OS (32 or 64 bits);
- Make sure you have a monitor, mouse and keyboard connected in the device, at least until you get SSH access to it.

##### Required softwares
- Raspberry PI ARM ONA image
- CERT NetSA Security Suite (Silk and YAF)

##### Step by step installation
1. Download the .deb for ONA and tar.gz's for SILK and YAF:
```bash
cd /tmp
wget https://onstatic.s3.amazonaws.com/ona/master/ona-service_RaspbianJessie_armhf.deb
wget https://tools.netsa.cert.org/releases/silk-3.19.2.tar.gz
wget https://tools.netsa.cert.org/releases/yaf-2.12.1.tar.gz
```

2. Install dependencies for compiling SILK and YAF:
```bash
sudo apt-get install build-essential libglib2.0-dev libfixbuf-dev libpcap-dev
```

3. Create ONA dirs for SILK and YAF binaries:
```bash
sudo mkdir /opt/silk /opt/yaf
```

4. Compile and install SILK:
```bash
tar -xvzf silk-3.19.2.tar.gz
cd silk-3.19.2
./configure --prefix=/opt/silk --with-libfixbuf
make && sudo make install
cd ..
```

5. Compile and install YAF:
```shell
tar -xvzf yaf-2.12.1.tar.gz
cd yaf-2.12.1
./configure --prefix=/opt/yaf
make && sudo make install
```

6. Install ONA services:
```bash
sudo apt install ./ona-service_RaspbianJessie_armhf.deb
```

7. After this last step, if you followed the SCA sensor guide, your sensor should be appearing within your SCA dashboard. Wait around 10-20min before the console start to show the netflows

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
