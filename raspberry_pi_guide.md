<!---
title: Cisco Secure Cloud Analytics (SCA) - ONA Sensor with Raspberry PI
author: 
- Bruno Fagioli (bgimenez@cisco)
- Iuri Mieiras (iuri@mieras.com)
revision: 0
--->
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
wget https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.2/ona-service_RaspbianJessie_armhf.deb
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


