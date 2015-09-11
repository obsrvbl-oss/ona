#!/usr/bin/env python

# configure NPR via Python script

import socket, sys, struct

actions = [ '', 'block', 'unblock', 'clear_all', 'whitelist' ]

def usage(prog) :
	options = '|'.join(actions[1:])
	print 'usage: %s (' % (prog) + options + ') IPADDR'
	sys.exit(1)

if (not (2 <= len(sys.argv)) and (len(sys.argv) <= 3)) :
	usage(sys.argv[0])

type = actions.index(sys.argv[1])
if type != actions.index('clear_all') :
	if len(sys.argv) != 3 :
		usage(sys.argv[0])
	value = sys.argv[2]
	if len(value.split('.')) == 4 :
		value = socket.inet_aton(value)
		value = struct.unpack('I', value)[0]
		value = socket.htonl(value)
else :
	value = 0

# destination address is hooked into NPR.1 port 1 filter
dst_tuple = ('192.168.1.1', 65535)
msg = struct.pack('II', socket.htonl(type), socket.htonl(value))

# Create a socket 
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Send the message
s.sendto(msg, dst_tuple)

# Close the socket
s.close()
