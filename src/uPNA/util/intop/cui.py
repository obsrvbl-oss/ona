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

#from profilers import profile

import curses, curses.panel, curses.ascii as ascii
import sys, string, optparse, time, os.path, re
from datetime import datetime, timedelta
import threading, time
from model import PNAModel
from monitor import DirectoryWatcher

# Main Curses interface handler
class CursesInterface :
    # constructor for the interface
    def __init__(self, screen, model, dirwatch) :
    #def __init__(self, screen, model, dirwatch) :
        self.screen = screen
        self.model = model
        self.handlers = []
        
        self.dirwatch = None
        if dirwatch != None :
            self.dirwatch = dirwatch
            self.dirwatch.begin()

        #self.dw = DirectoryWatcher(model, directory)
        #self.dw.begin()

        # build sub-windows and initialize windows
        self.windows = dict()
        (self.height, self.width) = self.screen.getmaxyx()

        window = curses.newwin(5, self.width, 0, 0)
        self.windows['settings'] = SettingsWindow(self, window)
    
        window = curses.newwin(self.height-4, self.width, 5, 0)
        self.windows['information'] = InfoWindow(self, window)

    # Add key press handler for the main interface
    def add_handler(self, keys, function) :
        self.handlers.append((keys, function))

    # Quit method
    def quit(self) :
        if self.dirwatch != None :
            self.dirwatch.end()
        #self.dw.end()
        sys.exit(0)

    # User/Display Interaction Loop
    def interact(self, update_freq=1) :
        while True :
            self.write_view()
            self.handle_control(update_freq)

    # Draws the view on the screen
    def write_view(self) :
        self.screen.refresh()
        for window in self.windows :
            self.windows[window].redraw()
        self.screen.move(0, self.width-1)

    # Get a key from curses.  This is a wrapper function because my computer
    # doesn't seem to register the arrow keys correctly
    def getkey(self, window, delay=1) :
        curses.halfdelay(delay*10)
        key = window.getkey()
        if len(key) > 1 :
            if key == 'KEY_DOWN' :
                key = curses.KEY_DOWN
            elif key == 'KEY_UP' :
                key = curses.KEY_UP
            elif key == 'KEY_LEFT' :
                key = curses.KEY_LEFT
            elif key == 'KEY_RIGHT' :
                key = curses.KEY_RIGHT
        elif ord(key) == ascii.ESC :
            # key begins escape sequence, decode
            curses.halfdelay(1)
            try :
                key = window.getkey()
            except curses.error :
                # this was just the escape key, return that
                return ascii.ESC
            if key == 'O' :
                # whole screen key press
                key = window.getkey()
                if key == 'A' :
                    key = curses.KEY_UP
                elif key == 'B' :
                    key = curses.KEY_DOWN
                elif key == 'C' :
                    key = curses.KEY_RIGHT
                elif key == 'D' :
                    key = curses.KEY_LEFT
            elif key == '[' :
                # window screen key press
                key = window.getkey()
                if key == 'A' :
                    key = curses.KEY_UP
                elif key == 'B' :
                    key = curses.KEY_DOWN
                elif key == 'C' :
                    key = curses.KEY_RIGHT
                elif key == 'D' :
                    key = curses.KEY_LEFT
                elif key == '3' :
                    # key is Apple escape sequence
                    key = window.getkey()
                    if key == '~' :
                        # key is Apple delete
                        key = ascii.DEL
        elif ord(key) == ascii.NAK :
            # key is a ctrl+u
            key = ascii.NAK
        elif ord(key) in (ascii.BS, ascii.US, ascii.DEL):
            # key is backspace
            key = ascii.BS
        elif ord(key) == ascii.FF :
            # key is form-feed (ctrl-l)
            key = ascii.FF
        elif ord(key) == ascii.DC2 :
            # key is ctrl-r (device control 2, block-mode)
            key = ascii.DC2
        return key

    # Handles user input and dispatch
    def handle_control(self, update_freq) :
        try :
            key = self.getkey(self.screen, update_freq)
        except curses.error :
            return
        for handler in self.handlers :
            if key in handler[0] :
                handler[1]()

class EditField :
    def __init__(self, interface, width, pos_y, pos_x) :
        # Configure the input window
        self.width = width
        self.interface = interface
        self.edit_box = curses.newwin(1, self.width, pos_y, pos_x)
        self.edit_pane = curses.panel.new_panel(self.edit_box)

    def get_value(self, initial='0', chars=string.letters) :
        value = initial
        position = len(value)
        while True :
            # Display view
            my_str = value + ('_'*(self.width - len(value) - 1))
            self.edit_box.addstr(0, 0, my_str, curses.A_REVERSE)
            self.edit_box.move(0, position)
            self.edit_box.refresh()

            # Interaction
            try :
                key = self.interface.getkey(self.edit_box)
            except curses.error :
                continue
            if key in ('\r','\n', curses.KEY_ENTER) :
                # value remains as-is
                break
            elif key in ('q','Q',ascii.ESC,) :
                # revert value to original
                value = initial
                break
            elif key in (curses.KEY_UP,) :
                # to beginning of line
                if position == 0 : curses.beep()
                position = 0
            elif key in (curses.KEY_DOWN,) :
                # to end of line
                if position == len(value) : curses.beep()
                position = len(value)
            elif key in (curses.KEY_LEFT,) :
                # move left one character
                if position <= 0 :
                    curses.beep()
                else :
                    position -= 1
            elif key in (curses.KEY_RIGHT,) :
                # move right one character
                if position > len(value)-1 :
                    curses.beep()
                else :
                    position += 1
            elif key in (ascii.BS,) :
                if position == 0 :
                    curses.beep()
                else :
                    # backspace
                    position -= 1
                    value = value[:position]+value[position+1:]
            elif key in (ascii.DEL,) :
                if position == len(value) :
                    curses.beep()
                else :
                    # delete
                    value = value[:position]+value[position+1:]
            elif key in (ascii.NAK,) :
                # clear entire string
                value = ''
                position = 0
            elif len(value) < self.width-2 and key in chars :
                # acceptable characters
                value = value[:position] + key + value[position:]
                position += 1
            else :
                # unrecognized
                curses.beep()
        self.edit_box.erase()

        return value

class SettingsWindow :
    def __init__(self, interface, window) :
        self.interface = interface
        self.window = window

        # for convenience
        (self.height, self.width) = window.getmaxyx()

        # register key handlers
        self.actions = [(('s','S',), 'Sort key', self.set_sort_key),
                        (('t','T',), 'Threshold', self.set_threshold),
                        (('f','F',), 'Filter(s)', self.view_filters),
                        #(('w','W',), 'Write File', self.write_file),
                        (('q','Q',ascii.ESC), 'Quit', self.interface.quit),]
        for action in self.actions :
            keys = action[0]
            function = action[2]
            self.interface.add_handler(keys, function)

    def redraw(self) :
        settings = self.interface.model.settings

        # Stringify the title bar
        my_str = ''
        program = '(intop)'
        for action in self.actions :
            my_str += action[0][0]+':'+action[1]+'  '
        my_str += ' '*(self.width-len(my_str)-len(program))
        my_str += program
        self.window.addstr(0, 0, my_str, curses.A_REVERSE)

        # Stringify the sort key
        my_str = '  Sort Key: '
        my_str += PNAModel.stringify(settings['sort-key'])
        self.window.addstr(1, 0, my_str)

        # Stringify the threshold
        my_str = ' Threshold: '
        my_str += str(settings['threshold'])
        self.window.addstr(2, 0, my_str)

        # Stringify the filters
        self.window.addstr(self.height-1, 0, ' '*(self.width-1))
        filter_str = '   Filters: '
        if settings['filters'] == None or settings['filters'] == {} :
            my_str = filter_str
            my_str += 'None'
            self.window.addstr(3, 0, my_str)
        else:
            for (i, filter) in enumerate(settings['filters']) :
                if i == 0 :
                    my_str = filter_str
                elif (i+3) >= self.height :
                    my_str = ' [press "f" for more filters]'
                    pos_y = self.width-len(my_str)-1
                    self.window.addstr(i+2, pos_y, my_str)
                    break
                else :
                    my_str = ' '*len(filter_str)
                my_str += PNAModel.stringify(filter) + ' of '
                my_str += str(settings['filters'][filter])
                my_str += ' '*(self.width-len(my_str)-1)
                self.window.addstr(i+3, 0, my_str)

        # move all the changes we've made to the actual screen
        self.window.refresh()

    # Display pop-up for selecting a sort key
    def set_sort_key(self) :
        settings = self.interface.model.settings
        current_key = settings['sort-key']

        # Get and format the available keys
        format = '%-15s'
        sort_keys = []
        for key in self.interface.model.sort_keys :
            sort_keys.append(format % PNAModel.stringify(key))

        # Build selection box
        key_box = curses.newwin(len(sort_keys)+2, len(sort_keys[0])+2, 0, 11)
        key_box.box()
        key_pane = curses.panel.new_panel(key_box)

        # Establish interface for selection box
        selection = list(self.interface.model.sort_keys).index(current_key)
        while True :
            # Display view
            for (i, key) in enumerate(sort_keys) :
                if i == selection :
                    key_box.addstr(i+1, 1, key, curses.A_REVERSE)
                else :
                    key_box.addstr(i+1, 1, key)
            key_box.move(selection+1, 1)
            key_box.refresh()

            # Interaction
            try :
                key = self.interface.getkey(key_box)
            except curses.error :
                continue
            if key in ('q','Q',ascii.ESC,) :
                break
            elif key in ('\r', '\n',) :
                settings['sort-key'] = self.interface.model.sort_keys[selection]
                break
            elif key in ('k', curses.KEY_UP,) :
                selection -= 1
                if selection < 0 :
                    selection = 0
                    curses.beep()
            elif key in ('j', curses.KEY_DOWN,) :
                selection += 1
                if selection > len(sort_keys) - 1 :
                    selection = len(sort_keys) - 1
                    curses.beep()
            elif key in ('h', curses.KEY_LEFT,) :
                if selection == 0 :
                    curses.beep()
                selection = 0
            elif key in ('l', curses.KEY_RIGHT,) :
                if selection == len(sort_keys) - 1 :
                    curses.beep()
                selection = len(sort_keys) - 1
        key_pane.hide()
        key_box.erase()
        self.interface.windows['information'].clear()

    def set_threshold(self) :
        # create an edit box
        edit_box = EditField(self.interface, 15, 2, 12)

        # find current value and get new value
        value = str(self.interface.model.settings['threshold'])
        value = edit_box.get_value(initial=value, chars=string.digits)

        # parse the value into number and save
        if value == '' :
            value = '0'
        value = int(value)
        if value > 4294967295 :
            value = 4294967295
        self.interface.model.settings['threshold'] = value
        self.interface.windows['information'].clear()

    def view_filters(self) :
        # Get and format the filter list
        name_len = 17
        value_len = 21
        format = ' %'+str(name_len)+'s: %-'+str(value_len)+'s'
        settings = self.interface.model.settings
        filters = []
        for filter in self.interface.model.filters :
            name_str = PNAModel.stringify(filter)
            value_str = settings['filters'].get(filter, '')
            my_str = format % (name_str, value_str)
            filters.append(my_str)

        # Build selection box
        filter_box = curses.newwin(len(filters)+2, len(filters[0])+2, 2, 11)
        filter_box.box()
        filter_pane = curses.panel.new_panel(filter_box)

        # Establish interface for selection box
        selection = 0
        while True :
            # Display view
            for (i, filter) in enumerate(filters) :
                if i == selection :
                    filter_box.addstr(i+1, 1, filter, curses.A_REVERSE)
                else :
                    filter_box.addstr(i+1, 1, filter)
            filter_box.move(selection+1, 1)
            filter_box.refresh()

            # Interaction
            try :
                key = self.interface.getkey(filter_box)
            except curses.error :
                continue
            if key in ('q','Q',ascii.ESC,) :
                break
            elif key in ('\r', '\n',) :
                # Get selected filter name
                filter = self.interface.model.filters[selection]
                regex = self.interface.model.filter_res[selection]

                filter_box.addstr(selection+1, 1, filters[selection])
                filter_box.refresh()

                # Get some settings
                value = settings['filters'].get(filter, '')
                chars = string.letters+string.digits+'.-:/ '
                y = selection+3
                x = 12+name_len+3

                # Get the new value (break on match)
                edit_box = EditField(self.interface, value_len, y, x)
                while True :
                    # find current value and get new value
                    value = edit_box.get_value(initial=value, chars=chars)

                    # see if value matches acceptable format
                    if value == '' or None != regex.match(value) :
                        break
                    curses.beep()
                if value == '' :
                    if filter in settings['filters'] :
                        del settings['filters'][filter]
                else :
                    settings['filters'][filter] = value
                name_str = PNAModel.stringify(filter)
                filters[selection] = format % (name_str, value)
            elif key in (ascii.BS, ascii.DEL,) :
                # Clear the selected filter
                filter = self.interface.model.filters[selection]
                if filter in settings['filters'] :
                    del settings['filters'][filter]
                name_str = PNAModel.stringify(filter)
                filters[selection] = format % (name_str, '')
            elif key in ('k', curses.KEY_UP,) :
                # Move selection up
                selection -= 1
                if selection < 0 :
                    selection = 0
                    curses.beep()
            elif key in ('j', curses.KEY_DOWN,) :
                # Move selection down
                selection += 1
                if selection > len(filters) - 1 :
                    selection = len(filters) - 1
                    curses.beep()
            elif key in ('h', curses.KEY_LEFT,) :
                # Move selection left
                if selection == 0 :
                    curses.beep()
                selection = 0
            elif key in ('l', curses.KEY_RIGHT,) :
                # Move selection right
                if selection == len(filters) - 1 :
                    curses.beep()
                selection = len(filters) - 1
        filter_pane.hide()
        filter_box.erase()
        self.interface.windows['information'].clear()

    def write_file(self) :
        pass

class InfoWindow :
    def __init__(self, interface, window) :
        self.interface = interface
        self.window = window
        self.selection = 0
        self.update_data()

        # for convenience
        (self.height, self.width) = self.window.getmaxyx()

        # register key handlers
        self.actions = [(('\r','\n',), 'View Details', self.view_details),
            (('k',curses.KEY_UP,), 'Up Selection', self.move_up),
            (('j',curses.KEY_DOWN,), 'Down Selection', self.move_down),
            (('h',curses.KEY_LEFT,), 'First Selection', self.move_first),
            (('l',curses.KEY_RIGHT,), 'Last Selection', self.move_last),
            (('r','R',ascii.FF,ascii.DC2), 'Update Data', self.update_data),]
        for action in self.actions :
            keys = action[0]
            function = action[2]
            self.interface.add_handler(keys, function)

    def clear(self) :
        self.window.erase()
        self.redraw()

    def redraw(self) :
        # clear the window, data might have changed
        self.window.erase()

        # formatting for the main view
        format = '%3s  %-15s  %-15s  %-19s  %-13s  %-13s'

        # fields, as specified by model
        fields = self.interface.model.get_fields()[0:5]
        headers = [PNAModel.stringify(f) for f in fields]
        headers.insert(0, '#')

        my_str = format % tuple(headers)
        self.window.addstr(0, 0, my_str, curses.A_REVERSE)

        # make sure we have the most up-to-date data
        self.update_data()

        for (i, item) in enumerate(self.data) :
            data = [ i+1 ]
            for f in fields :
                data.append(item[f])
            my_str = format % tuple(data)
            if self.selection == i :
                self.window.addstr(i+1, 0, my_str, curses.A_REVERSE)
            else :
                self.window.addstr(i+1, 0, my_str)

        # move all the changes we've made to the actual screen
        self.window.refresh()

    def update_data(self) :
        self.data = self.interface.model.get_data()
        (height, width) = self.window.getmaxyx()
        self.data = self.data[:height-2]
        if self.selection >= len(self.data) :
            self.selection = len(self.data) - 1
        elif self.selection < 0 and len(self.data) > 0:
            self.selection = 0

    def view_details(self) :
        # Make sure there is something available
        if 0 > self.selection or self.selection > len(self.data):
            curses.beep()
            return
        # Get and format the filter list
        name_len = 15
        value_len = 17
        format = ' %'+str(name_len)+'s: %-'+str(value_len)+'s'
        items = []
        max_width = 0
        for item in self.interface.model.get_fields(headers=False) :
            name = PNAModel.stringify(item)
            if item[0:3] in ('tcp', 'udp') and item[3:] == '-tuples' :
                ports = []
                for tuple in self.data[self.selection][item] :
                    local_port = str(tuple['local-port'])
                    remote_port = str(tuple['remote-port'])
                    ports.append(local_port+':'+remote_port)
                value = ', '.join(ports)
            else :
                value = str(self.data[self.selection][item])
            my_str = format % (name, value)
            if len(my_str) > self.width - 2:
                my_str = my_str[0:self.width-5]
                my_str += '...'
            if len(my_str) > max_width :
                max_width = len(my_str)
            items.append(my_str)

        # Build selection box
        x = (self.width - (max_width + 2)) / 2
        detail_box = curses.newwin(len(items)+2, max_width+2, 6, x)
        detail_box.box()
        detail_pane = curses.panel.new_panel(detail_box)

        # Establish interface for selection box
        while True :
            # Display view
            for (i, item) in enumerate(items) :
                detail_box.addstr(i+1, 1, item)
            detail_box.move(0,0)
            detail_box.refresh()

            # Interaction
            try :
                key = self.interface.getkey(detail_box)
            except curses.error :
                continue
            if key in ('q','Q',ascii.ESC,'\r','\n',) :
                break
        detail_pane.hide()
        detail_box.erase()

    def move_up(self) :
        self.selection -= 1
        if self.selection < 0 :
            self.selection = 0
            curses.beep()

    def move_down(self) :
        self.selection += 1
        if self.selection >= len(self.data) :
            self.selection = len(self.data)-1
            curses.beep()

    def move_first(self) :
        if self.selection == 0 :
            curses.beep()
        else :
            self.selection = 0

    def move_last(self) :
        if self.selection == len(self.data)-1 :
            curses.beep()
        else :
            self.selection = len(self.data)-1

class PNADirWatch(threading.Thread) :
    def __init__(self, directory, model, interval=1) :
        threading.Thread.__init__(self)
        self.interval = interval
        self.directory = directory
        self.model = model

    def run(self) :
        while True :
            for file in self.new_files() :
                self.model.add_file(file)
            time.sleep(self.interval)

    def new_files(self) :
        return []

def add_data(model, log_dir, begin, end) :
    if begin == None :
        begin = datetime.today() - timedelta(seconds=50, minutes=4)
        #print "begin", begin
    else :
        #begin = datetime(year=2010, month=10, day=5)
        b = re.search('(\d{4})(\d{2})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{6})?', begin)
        year = int(b.group(1))
        month = int(b.group(2))
        day = 1
        hour = minute = second = microsecond = 0
        if b.group(3) != None :
            day = int(b.group(3))
        if b.group(4) != None :
            hour = int(b.group(4))
        if b.group(5) != None :
            minute = int(b.group(5))
        if b.group(6) != None :
            second = int(b.group(6))
        if b.group(7) != None :
            microsecond = int(b.group(7))
        begin = datetime(year, month, day, hour, minute, second, microsecond)
        #print "begin", begin
    if end == None :
        end = datetime.today()
        #print "end", end
    else :
        e = re.search('(\d{4})(\d{2})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{6})?', end)
        year = int(e.group(1))
        month = int(e.group(2))
        #get last day of the month
        nextMonth = datetime(year, month+1, 1)
        delta = timedelta(seconds=1)
        numDay = nextMonth - delta
        day = numDay.day
        #print "day", day
        hour = 23
        minute = second = 59
        microsecond = 999999
        if e.group(3) != None :
            day = int(e.group(3))
        if e.group(4) != None :
            hour = int(e.group(4))
        if e.group(5) != None :
            minute = int(e.group(5))
        if e.group(6) != None :
            second = int(e.group(6))
        if e.group(7) != None :
            microsecond = int(e.group(7))
        end = datetime(year, month, day, hour, minute, second, microsecond)
        #print "end", end 

    item = ""
    for element in os.listdir(log_dir) :
        if string.find(element, ".") == 0 :
            continue
        item = log_dir
        item += element
        modified = os.path.getmtime(item)
        then = datetime.fromtimestamp(modified)
        #print "begin", begin
        #print "then", then
        #print "end", end
        if begin <= then and end >= then :
            #print "yes", item
            #print "modified time", then
            model.add_file(item)

def cui_main(screen, directory, static, begin, end) :
    # parse through the command line arguments (check if -d option)

    model = PNAModel()
   
    if static != None and directory != None :
         sys.exit(2)
    elif directory != None :
        add_data(model, directory, begin, end)
    elif static != None :
        add_data(model, static, begin, end)

    if directory :
        #print 'Directory to watch for updates needs to be specified'
        dirwatch = DirectoryWatcher(model, directory)
        interface = CursesInterface(screen, model, dirwatch)
        interface.interact()
    else :
        for file in args :
            model.add_file(file)
        interface = CursesInterface(screen, model, None)
        interface.interact()
        
    """
    # take the list of files and add them to the model
    for arg in sys.argv[1:] :
        model.add_file(arg)
    """
    #directory = sys.argv[2] 
    #interface = CursesInterface(screen, model, directory)
    #interface = CursesInterface(screen, model, )
    #interface.interact()

if __name__ == '__main__' :
    try :
        parser = optparse.OptionParser()
        parser.add_option('-d','--dynamic_directory',dest='directory',metavar='DIR', help='set CUI to watch directory DIR for updates; if this option is used, -s cannot be used')
        parser.add_option('-s','--static_directory',dest='static',metavar='DIR', help='directory of log files; if this option is used, -d cannot be used')
        parser.add_option('-b','--begin',dest='begin',metavar='BEGIN',help='set CUI to include data from BEGIN time in this format YYYYMMDDHHMMSSssssss. Unfilled fields are defauled with minimum values. By default, BEGIN is 5 minutes ago.')
        parser.add_option('-e','--end',dest='end',metavar='END',help='set CUI to include data until END time in this format YYYYMMDDHHMMSSssssss. Unfilled fields are defaulted with maximum values. By default, END is the current time.')
        (options, args) = parser.parse_args()
        curses.wrapper(cui_main, options.directory, options.static, options.begin, options.end)
        #cui_main(cui_main, options.directory, options.static, options.begin, options.end)
    except KeyboardInterrupt :
        sys.exit(1)
