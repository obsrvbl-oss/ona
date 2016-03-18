# Passive Network Appliance (PNA)

This software is designed to monitor all IP traffic arriving on a network interface.
It works by extracting header information from each packet in order to summarize
each flow. It periodially writes statistics out to disk so they can be analyzed.

## Building PNA

To build PNA you will need [libpcap](https://github.com/the-tcpdump-group/libpcap):

* Ubuntu and other Debian-based systems: Install the the `libpcap-dev` package.
* CentOS and other Red Hat-based systems: Install the `libpcap-devel` package.

Issue `make` in this top-level directory, and `module/pna` should be produced.
Confirm that it works with `./module/pna -h` - it should list available capture devices.

## Using PNA

PNA has several command line parameters:

* `-i <device>` - Specify a particular network interface (e.g., `eth1`)
* `-r <filename>` - Read from a stored .pcap file instead of a network interface
* `-o <directory>` - Specify a directory for output to be stored (default: `./logs`)
* `-Z <username>` - Drops privileges and switches to the given user after starting a capture
* `-N` - Specify a space-separated list of CIDR blocks to montior (default: `10.0.0.0/8 172.16.0.0/12 192.168.0.0/16`)
* `-v `- Verbose mode. Logs some statistics to stdout.

You may optionally specify a final argument representing a BPF expression. This will be used to filter the network data that's analyzed (e.g., `(not tcp port 80) and (not udp port 161)`). See the [pcap-filter man page](http://www.tcpdump.org/manpages/pcap-filter.7.htm) for information on using BPF expressions.

You should make sure the interface you want to monitor is up and in promiscuous mode. You can do this with `ifconfig`, for example:

```
ifconfig eth1 up promisc
```

### Examples

Simple capture on the `eth0` interface (using the default log directory):

```
# mkdir -p ./logs
# ./module/pna -i eth0
pna: capturing is available
Live capture from eth0
dumping to: './logs/pna-20150922154543-eth0.t0.log'
```

Verbose capturing to a specified log directory:

```
# mkdir -p ./wlan0_logs
# ./module/pna -i wlan0 -o ./wlan0_logs -v
flowmon memory: 114688 kibibytes (20 bits)
pna: capturing is available
pna_dtrie_add A000000/8 (1)
pna_dtrie_add AC100000/12 (2)
pna_dtrie_add C0A80000/16 (3)
Live capture from wlan0
=========================
Absolute Stats: 235 pkts rcvd, 0 pkts dropped
235 pkts [26.1 pkt/sec] - 64454 bytes [0.06 Mbit/sec]
=========================
dumping to: 'wlan0_logs/pna-20150922154920-wlan0.t1.log'
44 flows to 'wlan0_logs/pna-20150922154920-wlan0.t1.log'
```

Capturing from a network interface requires superuser privileges. You may invoke PNA with `sudo` and then use the `-Z` option to drop privileges and write files as a different user.

```
$ sudo ./module/pna -i wlan0 -Z some_user -v
flowmon memory: 114688 kibibytes (20 bits)
pna: capturing is available
pna_dtrie_add A000000/8 (1)
pna_dtrie_add AC100000/12 (2)
pna_dtrie_add C0A80000/16 (3)
Live capture from wlan0
dropping to user: some_user
```

Specifying networks to monitor and a packet filter:

```
$ mkdir ./eth1_logs
$ sudo ./module/pna -i eth1 -o ./wlan0_logs -Z some_user -N "192.168.12.0/24" -v
flowmon memory: 114688 kibibytes (20 bits)
pna: capturing is available
pna_dtrie_add C0A80C00/24 (1)
Live capture from eth1
dropping to user: some_user
```

## Analyzing the data

PNA writes logs in a special format to the output directory. You may use the scripts in the `util/intop` directory to parse the logs:

```
$./util/intop/cli.py logs/pna-20150922161203-wlan0.t0.log
```

## License

PNA is licensed under the terms of the Apache License, Version 2.0. Please see `LICENSE` for more details.
