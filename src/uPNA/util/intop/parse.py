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
import socket
import struct

EXTERNAL_NETID = 65535

__version__ = 'pna_parser_0.3.0-py'

# struct lengths with names
CHAR = 'c'
U_INT1 = 'B'
U_INT2 = 'H'
U_INT4 = 'I'


class PNALogParser(object):
    """This class parses a log file and returns the data contained within
    that file."""
    _header = {'v1a': (('start_time', U_INT4), ('end_time', U_INT4),
                       ('nentries', U_INT4)),
               'v2': (('magic0', CHAR), ('magic1', CHAR), ('magic2', CHAR),
                      ('version', U_INT1), ('start_time', U_INT4),
                      ('end_time', U_INT4), ('nentries', U_INT4))}
    _entry = {'v1': (('local_ip', U_INT4), ('remote_ip', U_INT4),
                     ('local_port', U_INT2), ('remote_port', U_INT2),
                     ('packets_out', U_INT4), ('packets_in', U_INT4),
                     ('octets_out', U_INT4), ('octets_in', U_INT4),
                     ('begin_time', U_INT4),
                     ('l4_protocol', U_INT1),
                     ('first_direction', U_INT1),
                     ('blank0', U_INT1), ('blank1', U_INT1)),
              'v1a': (('local_ip', U_INT4), ('remote_ip', U_INT4),
                      ('local_port', U_INT2), ('remote_port', U_INT2),
                      ('local_netid', U_INT2), ('remote_netid', U_INT2),
                      ('packets_out', U_INT4), ('packets_in', U_INT4),
                      ('octets_out', U_INT4), ('octets_in', U_INT4),
                      ('begin_time', U_INT4),
                      ('l4_protocol', U_INT1),
                      ('first_direction', U_INT1),
                      ('blank0', U_INT1), ('blank1', U_INT1)),
              'v2': (('local_ip', U_INT4), ('remote_ip', U_INT4),
                     ('local_port', U_INT2), ('remote_port', U_INT2),
                     ('local_netid', U_INT2), ('remote_netid', U_INT2),
                     ('packets_out', U_INT4), ('packets_in', U_INT4),
                     ('octets_out', U_INT4), ('octets_in', U_INT4),
                     ('local_flags', U_INT2), ('remote_flags', U_INT2),
                     ('begin_time', U_INT4), ('end_time', U_INT4),
                     ('l4_protocol', U_INT1),
                     ('first_direction', U_INT1),
                     ('blank0', U_INT1), ('blank1', U_INT1))}

    def __init__(self, filename):
        # open up the file descriptor for reading
        with open(filename, 'r') as f:
            self.data = f.read()
            self.data_len = len(self.data)
            self.position = 0
        # Figure out what log version this is
        if self.data[0:3] != "PNA":
            self.version = 'v1a'
        else:
            self.version = 'v%d' % ord(self.data[3])

        # Read in all the version fields
        self._set_header_type()
        self._set_entry_type()

        # Parse the header for useful info
        self.header = self.parse_header()
        self.entries_seen = 0

        # peek at the first entry to determine v1 or v1a
        if self.version == 'v1a':
            entry = self._ent_struct.unpack_from(self.data, self.position)
            entry = dict(zip(self._ent_names, entry))
            # if this is actually v1, the blanks are pushed to local_ip
            if entry['blank0'] != 0 or entry['blank1'] != 0:
                self.version = 'v1'
                self._set_entry_type()

    def _set_header_type(self):
        header = self._header[self.version]
        self._hdr_names = map(lambda x: x[0], header)
        header_format = map(lambda x: x[1], header)
        self._hdr_struct = struct.Struct(''.join(header_format))

    def _set_entry_type(self):
        entry = self._entry[self.version]
        self._ent_names = map(lambda x: x[0], entry)
        entry_format = map(lambda x: x[1], entry)
        self._ent_struct = struct.Struct(''.join(entry_format))

    def parse_header(self):
        """Parse only the header data, don't parse the file."""
        # read the header data first
        data = self._hdr_struct.unpack_from(self.data, self.position)
        self.position += self._hdr_struct.size
        return dict(zip(self._hdr_names, data))

    def parse_entry(self):
        """Parse a single entry from the file."""
        # read an entry
        entry = self._ent_struct.unpack_from(self.data, self.position)
        self.position += self._ent_struct.size
        # format the entry
        entry = dict(zip(self._ent_names, entry))
        if self.version in ('v1', 'v1a'):
            entry['l3_protocol'] = socket.IPPROTO_IPIP
            entry['local_flags'] = 0
            entry['remote_flags'] = 0
            entry['end_time'] = self.header['end_time']
            if self.version == 'v1':
                # version 1 does not have netids, so mimic what was expected
                entry['local_netid'] = 1
                entry['remote_netid'] = EXTERNAL_NETID
        return entry

    def parse(self):
        """Parse all entries, building a list."""
        sessions = []
        while self.position < self.data_len:
            sessions.append(self.parse_entry())
        return sessions

    def parse_cb(self, callback):
        """Parse all entries using specified callback function."""
        while self.position < self.data_len:
            callback(self.parse_entry())

    def parse_iter(self):
        """Parse all entries using generator pattern."""
        while self.position < self.data_len:
            yield self.parse_entry()


# simple command line version
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print 'version:', __version__
        print 'usage: %s <list of files>' % sys.argv[0]
        sys.exit(1)

    sessions = []
    for f in sys.argv[1:]:
        parser = PNALogParser(f)
        sessions.extend(parser.parse())
    print sessions
