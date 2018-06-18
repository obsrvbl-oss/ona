#  Copyright 2018 Observable Networks
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import print_function, unicode_literals

import logging

from binascii import hexlify
from collections import defaultdict
from json import dumps
from logging.handlers import TimedRotatingFileHandler
from os import environ
from os.path import join
from socket import AF_INET6, inet_ntoa, inet_ntop
from SocketServer import BaseRequestHandler, UDPServer
from struct import Struct, unpack
from utils import create_dirs

ENV_NVZFLOW_LOG_DIR = 'OBSRVBL_NVZFLOW_LOG_DIR'
DEFAULT_NVZFLOW_LOG_DIR = './logs'

ENV_NVZFLOW_LOG_LIMIT = 'OBSRVBL_NVZFLOW_LOG_LIMIT'
DEFAULT_NVZFLOW_LOG_LIMIT = '2880'


# Module logger - this is distinct from the file logger used by the writing
# process

def get_module_logger(name=None):
    name = name or __name__
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    return logger


logger = get_module_logger('nvzflow_reader')


# Struct definitions for reading IPFIX message fields

IPFIXHeader = Struct(
    b'!'  # network order
    b'H'  # Version Number (version)
    b'H'  # Length (len)
    b'I'  # Export Time (timestamp)
    b'I'  # Sequence Number (sequence)
    b'I'  # Observation Domain ID (od_id)
)

FlowSetHeader = Struct(
    b'!'  # network order
    b'H'  # flowset_id
    b'H'  # flowset_length
)

TemplateHeader = Struct(
    b'!'  # network order
    b'H'  # template_id
    b'H'  # template_field_count
)

TemplateField = Struct(
    b'!'  # network order
    b'H'  # template_ipfix_field_type
    b'H'  # template_field_length
)

TemplateFieldPEN = Struct(
    b'!'  # network order
    b'H'  # template_ipfix_field_type
    b'H'  # template_ipfix_field_length
    b'L'  # template_ipfix_field_pen
)

# Formatters for transforming packed IPFIX representation to human-readable
# data

FIELD_FORMATTERS = {
    (None, 4): {
        'name': 'protocolIdentifier',
        'formatter': lambda x: unpack(b'!B', x)[0],
    },
    (None, 8): {
        'name': 'sourceIPv4Address',
        'formatter': inet_ntoa,
    },
    (None, 7): {
        'name': 'sourceTransportPort',
        'formatter': lambda x: unpack(b'!H', x)[0],
    },
    (None, 11): {
        'name': 'destinationTransportPort',
        'formatter': lambda x: unpack(b'!H', x)[0],
    },
    (None, 12): {
        'name': 'destinationIPv4Address',
        'formatter': inet_ntoa,
    },
    (None, 27): {
        'name': 'sourceIPv6Address',
        'formatter': lambda x: inet_ntop(AF_INET6, x)
    },
    (None, 28): {
        'name': 'destinationIPv6Address',
        'formatter': lambda x: inet_ntop(AF_INET6, x),
    },
    (None, 150): {
        'name': 'flowStartSeconds',
        'formatter': lambda x: unpack(b'!I', x)[0],
    },
    (None, 151): {
        'name': 'flowEndSeconds',
        'formatter': lambda x: unpack(b'!I', x)[0],
    },
    (None, 350): {
        'name': 'virtualStationName',
        'formatter': lambda x: x.decode('utf-8', errors='ignore'),
    },
    (9, 12346): {
        'name': 'nvzFlowL4ByteCountIn',
        'formatter': lambda x: int(hexlify(x), 16),
    },
    (9, 12347): {
        'name': 'nvzFlowL4ByteCountOut',
        'formatter': lambda x: int(hexlify(x), 16),
    },
    (9, 12332): {
        'name': 'nvzFlowUDID',
        'formatter': lambda x: hexlify(x),
    },
}

# Cached templates (this is against RFC 7011)
NVZFLOW_TEMPLATE = {
    127: {
        262: [
            {'PEN': None, 'length': 65535, 'type': 350},
            {'PEN': 9, 'length': 20, 'type': 12332},
            {'PEN': 9, 'length': 65535, 'type': 12334},
            {'PEN': 9, 'length': 65535, 'type': 12335},
            {'PEN': 9, 'length': 65535, 'type': 12351},
            {'PEN': 9, 'length': 65535, 'type': 12336},
            {'PEN': 9, 'length': 65535, 'type': 12337}
        ],
        266: [
            {'PEN': 9, 'length': 20, 'type': 12332},
            {'PEN': 9, 'length': 4, 'type': 12355},
            {'PEN': 9, 'length': 4, 'type': 12356},
            {'PEN': 9, 'length': 1, 'type': 12357},
            {'PEN': 9, 'length': 65535, 'type': 12358},
            {'PEN': 9, 'length': 65535, 'type': 12359},
            {'PEN': 9, 'length': 65535, 'type': 12360}
        ],
        267: [
            {'PEN': None, 'length': 1, 'type': 4},
            {'PEN': None, 'length': 4, 'type': 8},
            {'PEN': None, 'length': 2, 'type': 7},
            {'PEN': None, 'length': 4, 'type': 12},
            {'PEN': None, 'length': 2, 'type': 11},
            {'PEN': None, 'length': 4, 'type': 150},
            {'PEN': None, 'length': 4, 'type': 151},
            {'PEN': 9, 'length': 20, 'type': 12332},
            {'PEN': 9, 'length': 65535, 'type': 12333},
            {'PEN': 9, 'length': 2, 'type': 12361},
            {'PEN': 9, 'length': 65535, 'type': 12338},
            {'PEN': 9, 'length': 2, 'type': 12362},
            {'PEN': 9, 'length': 65535, 'type': 12340},
            {'PEN': 9, 'length': 32, 'type': 12341},
            {'PEN': 9, 'length': 65535, 'type': 12339},
            {'PEN': 9, 'length': 2, 'type': 12363},
            {'PEN': 9, 'length': 65535, 'type': 12342},
            {'PEN': 9, 'length': 32, 'type': 12343},
            {'PEN': 9, 'length': 8, 'type': 12346},
            {'PEN': 9, 'length': 8, 'type': 12347},
            {'PEN': 9, 'length': 65535, 'type': 12344},
            {'PEN': 9, 'length': 65535, 'type': 12345},
            {'PEN': 9, 'length': 4, 'type': 12355},
            {'PEN': 9, 'length': 65535, 'type': 12352},
            {'PEN': 9, 'length': 65535, 'type': 12353}
        ],
        268: [
            {'PEN': None, 'length': 1, 'type': 4},
            {'PEN': None, 'length': 16, 'type': 27},
            {'PEN': None, 'length': 2, 'type': 7},
            {'PEN': None, 'length': 16, 'type': 28},
            {'PEN': None, 'length': 2, 'type': 11},
            {'PEN': None, 'length': 4, 'type': 150},
            {'PEN': None, 'length': 4, 'type': 151},
            {'PEN': 9, 'length': 20, 'type': 12332},
            {'PEN': 9, 'length': 65535, 'type': 12333},
            {'PEN': 9, 'length': 2, 'type': 12361},
            {'PEN': 9, 'length': 65535, 'type': 12338},
            {'PEN': 9, 'length': 2, 'type': 12362},
            {'PEN': 9, 'length': 65535, 'type': 12340},
            {'PEN': 9, 'length': 32, 'type': 12341},
            {'PEN': 9, 'length': 65535, 'type': 12339},
            {'PEN': 9, 'length': 2, 'type': 12363},
            {'PEN': 9, 'length': 65535, 'type': 12342},
            {'PEN': 9, 'length': 32, 'type': 12343},
            {'PEN': 9, 'length': 8, 'type': 12346},
            {'PEN': 9, 'length': 8, 'type': 12347},
            {'PEN': 9, 'length': 65535, 'type': 12344},
            {'PEN': 9, 'length': 65535, 'type': 12345},
            {'PEN': 9, 'length': 4, 'type': 12355},
            {'PEN': 9, 'length': 65535, 'type': 12352},
            {'PEN': 9, 'length': 65535, 'type': 12353}
        ]
    }
}

# IPFIX (RFC 7011) constants

VARIABLE_LENGTH_INDICATOR = 65535
VARIABLE_LENGTH_CONTINUATION = 255


# UDP datagram receiver

class NVZFlowHandler(BaseRequestHandler):
    def handle(self):
        global nvzflow_reader
        data = self.request[0]
        # Exceptions are caught in the nvzflow_reader object so the server
        # doesn't crash
        nvzflow_reader.handle_message(data)


# nvzflow interpreter - accepts data and writes it to timed log files

class NVZFlowReader(object):
    def __init__(self, known_templates=None):
        self.known_templates = known_templates or {}
        self.parsed_flows = []
        self.logger = self._get_file_logger()

    def _get_file_logger(self):
        # Output file logger - outputs once per minute
        file_dir = environ.get(ENV_NVZFLOW_LOG_DIR, DEFAULT_NVZFLOW_LOG_DIR)
        create_dirs(file_dir)

        file_handler = TimedRotatingFileHandler(
            join(file_dir, 'nvzflow.log'),
            when='m',
            interval=1,
            backupCount=int(
                environ.get(ENV_NVZFLOW_LOG_LIMIT, DEFAULT_NVZFLOW_LOG_LIMIT)
            ),
            utc=True,
        )

        file_logger = logging.getLogger('nvzflow_reader_ouput')
        file_logger.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(message)s'))
        file_logger.addHandler(file_handler)

        return file_logger

    def _parse_template_set(self, data, flowset_length, i):
        ret = defaultdict(list)
        stop = i + flowset_length - FlowSetHeader.size
        while i < stop:
            template_header = TemplateHeader.unpack_from(data, i)
            i += TemplateHeader.size
            template_id = template_header[0]
            template_field_count = template_header[1]

            for __ in range(template_field_count):
                template_field = TemplateField.unpack_from(data, i)

                # If the first bit is set, the template is for a Private
                # Enterprise Information Element
                if template_field[0] & 0x8000:
                    template_field = TemplateFieldPEN.unpack_from(data, i)
                    i += TemplateFieldPEN.size
                    template_field_type = template_field[0] & 0x7fff
                    template_field_pen = template_field[2]
                # Otherwise, it's for a standard element
                else:
                    i += TemplateField.size
                    template_field_type = template_field[0]
                    template_field_pen = None

                template_field_length = template_field[1]
                item = {
                    'type': template_field_type,
                    'length': template_field_length,
                    'PEN': template_field_pen,
                }
                ret[template_id].append(item)

        return ret

    def _parse_data_set(self, data, flowset_length, i, flowset_template):
        stop = i + flowset_length - FlowSetHeader.size
        while i < stop:
            flow = []
            for element in flowset_template:
                key = element['PEN'], element['type']

                length = element['length']
                if length == VARIABLE_LENGTH_INDICATOR:
                    length = unpack(b'!B', data[i:i + 1])[0]
                    i += 1
                    if length == VARIABLE_LENGTH_CONTINUATION:
                        length = unpack(b'!H', data[i:i + 2])[0]
                        i += 2

                value = data[i:i + length]
                i += length

                flow.append((key, value))

            yield flow

    def update_from_message(self, data):
        i = 0

        # Parse the message header
        ipfix_header = IPFIXHeader.unpack_from(data, i)
        i += IPFIXHeader.size
        message_version = ipfix_header[0]
        message_length = ipfix_header[1]
        od_id = ipfix_header[4]

        if message_version != 10:
            raise ValueError('wrong version detected')

        od_templates = self.known_templates.setdefault(od_id, {})

        # Parse the flow sets
        while i < message_length:
            flowset_header = FlowSetHeader.unpack_from(data, i)
            i += FlowSetHeader.size
            flowset_id = flowset_header[0]
            flowset_length = flowset_header[1]

            # Templates always come with ID=2
            if flowset_id == 2:
                message_templates = self._parse_template_set(
                    data, flowset_length, i
                )
                od_templates.update(message_templates)
            # Data always comes with ID >= 256
            elif flowset_id >= 256:
                if flowset_id in od_templates:
                    flowset_template = od_templates[flowset_id]
                    self.parsed_flows.extend(
                        self._parse_data_set(
                            data, flowset_length, i, flowset_template
                        )
                    )
                else:
                    logger.warning('Unknown template {}'.format(flowset_id))
            # TODO: Handle Options Templates (ID=3)
            else:
                logger.error('Unknown flowset id {}'.format(flowset_id))

            i += flowset_length - FlowSetHeader.size

        self.known_templates[od_id] = od_templates

    def get_formatted_flows(self):
        for in_flow in self.parsed_flows:
            out_flow = {}
            for key, value in in_flow:
                if key in FIELD_FORMATTERS:
                    mapper = FIELD_FORMATTERS[key]
                    element_name = mapper['name']
                    element_value = mapper['formatter'](value)
                    out_flow[element_name] = element_value

            if out_flow:
                yield out_flow

    def write_log(self, formatted_flows):
        for flow in formatted_flows:
            self.logger.info(dumps(flow, sort_keys=True))

    def handle_message(self, data):
        # Populate self.known_templates and self.parsed_flows and then
        # write the formatted flows to disk
        try:
            self.update_from_message(data)
            self.write_log(self.get_formatted_flows())
        # Don't crash on bad input
        except Exception:
            logger.exception('Could not read request')
        # Clean up stored flows
        finally:
            self.parsed_flows = []


# Global reader is set when running as a module
nvzflow_reader = None

if __name__ == '__main__':
    receive_host = environ.get('OBSRVBL_NVZFLOW_RECEIVE_HOST', '0.0.0.0')
    receive_port = int(
        environ.get('OBSRVBL_NVZFLOW_RECEIVE_PORT', '2055')
    )
    logger.info('Listening on %s:%s', receive_host, receive_port)
    nvzflow_reader = NVZFlowReader(known_templates=NVZFLOW_TEMPLATE)
    server = UDPServer((receive_host, receive_port), NVZFlowHandler)
    server.serve_forever()
