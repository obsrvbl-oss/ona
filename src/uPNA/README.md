# Passive Network Appliance Node Software #

This software is designed to monitor all traffic arriving at a network
card, extract summary statistics, insert that packet into a flow table, and
periodically dump that flow table to a file on disk.

This is a user-space version that generates a binary compatible format with
the higher-performance kernel-space version.

## Instructions ##

Building can be done by typing `make` in the top level directory.  This
will build the user-space module (found in `module/`).

Loading the kernel module and user-space programs is done with a script
(`pna-service`).  This script has a few configuration parameters that should
be set (in `config/monitor`):

 - `PNA_IFACE` sets the interfaces on which traffic will be monitored
 - `PNA_LOGDIR` sets the location to store the logged statistics

Depending on your network, you can also set the `config/networks` file to
include the networks to monitor. By default this is the three private
networks (`10.0.0.0/8`, `172.16.0.0/12`, and `192.168.0.0/16`).

Multiple interfaces are supported by setting `PNA_IFACE` to a
comma-separated list. For example, `PNA_IFACE=eth0,eth1,eth2` will start a
separate process listening on each of those interfaces.

Nothing else should need modification.

The script can be run by typing `make start` from the top level directory.
This will load the kernel module and start the user-space programs.  If
there is traffic, log files should appear in `PNA_LOGDIR` after 10 seconds.
You can stop all the software at any time by running `make stop` from the
top level directory.  This will unload the kernel module and kill any
user-space processes.

Optionally, there are scripts in `util/cron/` that can be used to move the
log files elsewhere as needed.  There is also a command line interface
`util/intop/cli.py` that can process log files and print out the summary
statistics in a useful format.

## File Manifest ##

Below is an approximate description of the various folders and files in
this project.

 - `include/` contains the header file(s) for the PNA software
 - `module/` contains the kernel module source code
   - `pna.c` is the main entry point for the program, it handle the libpcap
     wrapping
   - `pna_main.c` is the entry point for the dispatching packets to
     sub-routines (initialization and hooking)
   - `pna_flowmon.c` has routines to insert the packet into a flow entry
     and deals with exporting the summary statistics to user-space
   - `pna_rtmon.c` is the handler for real-time monitors
   - `pna_config.c` handles run-time configuration parameters
 - `pna-service` is the script to start and stop all the PNA software
 - `util/cron/` contains scripts and crontabs that help move files off-site
 - `util/intop/` contains software to help read and process the log files

## License ##

Copyright 2011 Washington University in St Louis

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

> Please see `LICENSE` for more details.
