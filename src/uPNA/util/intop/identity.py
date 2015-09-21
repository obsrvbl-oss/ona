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

# The goal of this file is to take a log file, python-ize the data, then
# convert it back to a log file.  Or simply take python-ized data and create a
# log file.

# Going from log->python should be easy...
from parse import PNALogParser

import sys, struct

# This should move from python->log format
class PNAParseLogger :
    @classmethod
    def unparse(cls, raw_data) :
        file_data = ''
        for item in raw_data :
            # get top-level items
            end_time = item['end-time']
            watch_data = item['watch-data']
            entry_data = ''
            for entry in watch_data :
                # get second-level items
                lip = entry['local-ip']
                rip = entry['remote-ip']
                ntcp = entry['ntcp']
                nudp = entry['nudp']
                tcp_tuples = entry['tcp-tuples']
                udp_tuples = entry['udp-tuples']
                # parse the port tuples
                tcp_data = ''
                for t in tcp_tuples :
                    # ugly, but temporary...
                    a = t['local-port']
                    b = t['remote-port']
                    c = t['npkts-in']
                    d = t['npkts-out']
                    e = t['nbytes-in']
                    f = t['nbytes-out']
                    g = t['begin-time']
                    h = t['first-direction']
                    tcp_data += struct.pack('HHIIIIIBxxx',a,b,c,d,e,f,g,h)
                udp_data = ''
                for t in udp_tuples :
                    # ugly, but temporary...
                    a = t['local-port']
                    b = t['remote-port']
                    c = t['npkts-in']
                    d = t['npkts-out']
                    e = t['nbytes-in']
                    f = t['nbytes-out']
                    g = t['begin-time']
                    h = t['first-direction']
                    udp_data += struct.pack('HHIIIIIBxxx',a,b,c,d,e,f,g,h)
                # aggregate data for an entry
                entry_data += struct.pack('IIII',lip,rip,ntcp,nudp)
                entry_data += tcp_data + udp_data
            # aggregate and find length for item
            file_data += struct.pack('II', end_time, len(entry_data))
            file_data += entry_data
        return file_data

def main(args) :
    # convert each command line file individually
    for arg in args :
        print 'identity of "'+arg+'" is "'+arg+'.id"'
        if arg[-5:] == '.dict' :
            # just need to unparse
            f = open(arg, 'r')
            data = f.read()
            f.close()
            raw_data = eval(data)
            file_data = PNAParseLogger.unparse(raw_data)
        else :
            raw_data = PNALogParser.parse(arg)
            file_data = PNAParseLogger.unparse(raw_data)
        file = open(arg+'.id', 'w')
        file.write(file_data)
        file.close()

if __name__ == '__main__' :
    main(sys.argv[1:])
