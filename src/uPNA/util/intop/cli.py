#!/usr/bin/env python
#
# Copyright 2011 Washington University in St Louis
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import optparse
import time
from model import PNAModel

try:
    import json
    has_json = True
except:
    has_json = False


class CommandLineInterface(object):
    def __init__(self, arguments, model):
        self.arguments = arguments
        self.model = model

    # begin the "interaction" part
    def interact(self):
        formats = [f for f in dir(self) if f[-7:] == '_format']

        usage = 'usage: %prog [options] <list of files>\n'
        usage += 'FORMAT can be: ' + ', '.join(f[:-7] for f in formats)

        # create the option parser for command line args
        argparse = optparse.OptionParser(usage=usage)
        argparse.add_option('-f', '--format', dest='format', metavar='FORMAT',
                            help='set output format to FORMAT',
                            default='python')
        # filters from model.py
        #  local-ip, remote-ip, source-port, destination-port, begin-time,
        #  end-time
        argparse.add_option('-l', '--local-ip', dest='local_ip', metavar='IP',
                            help='display local IPs matching IP',
                            default=None)
        argparse.add_option('-r', '--remote-ip', dest='remote_ip',
                            metavar='IP',
                            help='display remote IPs matching IP',
                            default=None)
        #argparse.add_option('-lpt', '--local-port', dest='local_port',
        #                    metavar='PORT',
        #                    help='only display local ports that match PORT',
        #                    default=None)
        #argparse.add_option('-rpt', '--remote-port', dest='remote_port',
        #                    metavar='PORT',
        #                    help='only display remote ports that match PORT',
        #                    default=None)
        argparse.add_option(
            '-b', '--begin-time', dest='begin_time', metavar='TIME',
            help='display flows starting after TIME ('+self.model.time_fmt+')',
            default=None)
        argparse.add_option(
            '-e', '--end-time', dest='end_time', metavar='TIME',
            help='display flows ending before TIME ('+self.model.time_fmt+')',
            default=None)
        (options, files) = argparse.parse_args(self.arguments)

        # get the print format routine
        try:
            print_format = getattr(self, options.format+'_format')
        except AttributeError:
            argparse.print_help()
            sys.exit(1)

        # make sure we have files to parse
        if len(files) == 0:
            argparse.print_help()
            sys.exit(1)

        # TODO: configure model with command line args
        # options.sort_key
        # options.threshold
        # options.filters
        self.model.settings['sort-key'] = 'raw'
        self.model.settings['threshold'] = 0
        self.model.settings['filters'] = {}
        if options.local_ip:
            self.model.settings['filters']['local-ip'] = options.local_ip
        if options.remote_ip:
            self.model.settings['filters']['remote-ip'] = options.remote_ip
        if options.begin_time:
            self.model.settings['filters']['begin-time'] = options.begin_time
        if options.end_time:
            self.model.settings['filters']['end-time'] = options.end_time

        # Add each file in the list to the model
        for file in files:
            self.model.add_file(file)

        # get_data() from the model, this will be filtered
        data = self.model.get_data(raw=True)
        print_format(data)

    # dump the data in a the raw python format
    def python_format(self, data):
        print data

    # dump the data in Javascript JSON format
    def json_format(self, data):
        if has_json:
            print json.dumps(data)
        else:
            print 'json unavailable'

    # dump the data in flow-tools' flow-print -f5 format
    def flow_format(self, data):
        fmt = ('%-17s %-17s %-5s %-15s %-5s %-5s %-15s %-5s '
               '%3s %-2s %-10s %-22s')
        time_fmt = '%m%d.%H:%M:%S.000'

        display = ('Start', 'End', 'Sif', 'SrcIPaddress', 'SrcP', 'Dif',
                   'DstIPaddress', 'DstP', 'P', 'Fl', 'Pkts', 'Octets')

        # header
        print fmt % display

        for log in data:
            end_time = time.localtime(log['start_time'])
            end = time.strftime(time_fmt, end_time)
            for f in log['flows']:
                src_ip = self.int2ip(f['local_ip'])
                dst_ip = self.int2ip(f['remote_ip'])
                sif = '0'
                dif = '0'

                proto = f['l4_protocol']
                start_time = time.localtime(f['begin_time'])
                start = time.strftime(time_fmt, start_time)
                src_pt = str(f['local_port'])
                dst_pt = str(f['remote_port'])
                npkts = str(f['packets_in']+f['packets_out'])
                nbytes = str(f['octets_in']+f['octets_out'])
                flags = hex(f['local_flags'] | f['remote_flags'])
                entry = (start, end, sif, src_ip, src_pt, dif, dst_ip,
                         dst_pt, proto, flags, npkts, nbytes)
                print fmt % entry

    # convert an ip-as-integer to a string
    def int2ip(self, addr):
        octet = (addr >> 24 & 0xff, addr >> 16 & 0xff,
                 addr >> 8 & 0xff, addr & 0xff)
        return '.'.join([str(o) for o in octet])


def main(arguments):
    model = PNAModel()
    interface = CommandLineInterface(arguments, model)
    interface.interact()

# start the program
if __name__ == '__main__':
    main(sys.argv[1:])
