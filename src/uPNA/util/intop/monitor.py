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

import pyinotify
import time
from model import PNAModel

class EventHandler(pyinotify.ProcessEvent):

    def __init__(self, model):
	self.model = model

    def process_IN_CREATE(self, event):
        #print "Creating:", event.pathname
	self.model.add_file(event.pathname)

class DirectoryWatcher():
	wm = pyinotify.WatchManager()  # Watch Manager
	mask = pyinotify.IN_CREATE # watched events

	def __init__(self, model, directory):
		self.directory = directory
		self.eh = EventHandler(model)
		self.notifier = pyinotify.ThreadedNotifier(self.wm, self.eh)
		self.wdd = dict()

	def begin(self):
		self.notifier.start()
		self.wdd = self.wm.add_watch(self.directory, self.mask, rec=True)

	def end(self):
		self.wm.rm_watch(self.wdd.values())
		self.notifier.stop()

#try :
#	notifier.start()
#	wdd = wm.add_watch('/home/ryoung/intop-ports/storage/', mask, rec=True)
	#wm.rm_watch(wdd.values())

#	print 'eh.i', eh.i

#	while 1 :
#		if eh.i >= 3 :
#	  		print '>= 3'
#			break
			#wm.rm_watch(wdd.values())
			#notifier.stop()
		#time.sleep(5)
#	wm.rm_watch(wdd.values())
#	notifier.stop()
		#notifier.process_events()
		#if notifier.check_events() :
		#	notifier.read_events()

#	print "middle try"
	
#except KeyboardInterrupt:
#	notifier.stop()

