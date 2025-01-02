#!/usr/bin/env python 
'''
X-Tool D1 machine class for K40 Whisperer

Copyright (C) 2024 whodafloater

MIT licsence

'''
#try:
#    import usb.core
#    import usb.util
#    import usb.backend.libusb0
#except:
#    print("Unable to load USB library (Sending data to Laser will not work.)")

import sys
import struct
import os
from shutil import copyfile
from egv import egv
import traceback
from windowsinhibitor import WindowsInhibitor
import time
import requests
import json
import math
import re

import threading
import queue

from dataclasses import dataclass, field
from typing import Any

@dataclass(order=True)
class Xmsg:
    priority: int
    item: Any=field(compare=False)

##############################################################################

class xtool_CLASS:
    def __init__(self):
        self.what_i_aspire_to_be = 'xTool D1'
        self.dev        = None
        self.IP = '192.168.0.106'
        self.PORT = 8080

        self.online_status = False

        self.n_timeouts = 10
        self.timeout    = 200   # Time in milliseconds

        self.flipy = True
        self.dialect = 'ecoord'
        self.state = 0

        self.linear_rapid = 3000/60  # mm/s

        self.spindle_power_scale = 10
        self.safety_power_scale = 1.0

        # these are for pause and re-start
        self.paused = False
        self.sendi = 0;
        self.sendstates=[]

        self.debug = False

        # for tracking machine state
        self.__drlocx = 0
        self.__drlocy = 0
        if self.flipy: self.__yflip = -1
        else:          self.__yflip = 1
        self.__feed = 0
        self.__power = 0
        self.__cross = 0
        self.__working = '?'


        self.q = queue.PriorityQueue()
        self.lock = threading.Lock()
        self.start()
        self.lock.acquire()
        self.lock.release()

        #for param in self.__dict__:
        #   print(f'xtool_lib: param: {param}')

    def worker(self):
        #   Xmsg(priority, message)
        #   message must be a tuple
        #   self.k40.q.put(Xmsg(0, ("junk", 'hello', 'bye', 3.14)))
        #   self.k40.q.put(Xmsg(2, ("abort", 'hello', 'timeout:4.5', 'name=foo')))
        #   self.k40.q.put(Xmsg(2, ("abort", 'hello', '{timeout:4.5, name:foo}')))
        #   self.k40.q.put(Xmsg(2, ("get_status",)))
        #   self.k40.junk()
        #   self.k40.junk('one', 'two', time=6, timeout=89)
        #   self.k40.q.put(Xmsg(9, ("rapid_move", 1000, 1000)))
        #   self.k40.q.put(Xmsg(2, ("get_status",)))
        #   self.k40.q.put( Xmsg(9, ("rapid_move(1000, 1000)",) ))
        #   self.k40.q.put( Xmsg(9, "rapid_move(1000, 1000)" ) )

        exit_request = False

        while True:
            if self.q.empty() and exit_request:
               break

            pi = self.q.get()
            #print(f'\n\nWorking on: pri:{pi.priority}  item:{pi.item}    nargs={len(pi.item)}')

            raw = pi.item
            if len(raw) == 0:
               self.q.task_done()
               continue

            command = ''
            itemargs = []
            lastarg = ''
            if len(raw[0]) == 1:
                # assume this is really a single string, accidently given as a tuple of chars
                accum = ''
                np = 0
                for c in raw:
                    accum = accum + c
                    if c == '(':
                        raise Exception(f'I am not a parser. Input was: {raw}')

                command = accum
                print(f'    command: {command:20s} {itemargs}   lastarg={lastarg}')
            else: 
                nargs = len(pi.item)
                command = pi.item[0]
                itemargs = pi.item[1:nargs]  
                lastarg = pi.item[nargs-1]
                print(f'    command: {command:20s} {itemargs}   lastarg={lastarg}')

            kwargs = dict()
            args = []

            if command == 'exit':
                exit_request = True

            if command == 'kill':
                break;

            for n in itemargs:
            #    print(f'  arg: {n}')
                if ':' in str(n):
                     f = re.split(r'[() \t:{}]+', n)
                     if f[0] == '': f.pop(0)
            #         print(f'  found a dict: {n}   {f}')
                     while len(f) > 1:
                        key = f.pop(0)
                        val = f.pop(0)
                        kwargs[key]=val
                else:
                     args.append(n)

            #print(f'   args:  {args}')
            #print(f' kwargs:  {kwargs}')
            print(f'    command: {command:20s} {args} {kwargs}')

            try: 
                method = getattr(self, command)
                method(*args, **kwargs)
            except AttributeError:
                print(f' not implemented: {command}')

            #time.sleep(1)
            #print(f'Finished {pi}')
            self.q.task_done()
        return 

    def start(self):
        self.worker = threading.Thread(target=self.worker, daemon=True)
        self.worker.start()

    def junk(self, *args, **kwargs):
        print(f'------------------ xtool_lib:  junk args:{args}   kw:{kwargs}')

    def abort(self, *args, **kwargs):
        print(f'------------------ xtool_lib:  abort args:{args}  kw:{kwargs}')

    def initialize_device(self, Location=None, Port=8080, verbose=False):
        self.lock.acquire()
        """
        Just establish we can talk to a thing
        and the thing is what we expect
        No machine setup in here

        In the K40 driver this function inits the USB 'device'
        """
        # just ping the ip and see if any body is there. May not even be the Xtool
        if Location != None:
            self.IP = Location
        if Port != None:
            self.PORT = Port

        reply = ''
        try:
            reply = self._get_request('', timeout=1).decode('utf-8')
        except requests.exceptions.ConnectTimeout:
            self.online_status = False
            self.lock.release()
            raise Exception(f'No Response from {self.__lasturl}')

        self.online_status = True

        # see if device reports a name
        d = dict()
        try:
            d = self.blast(['/system?action=get_dev_name'])
        except requests.exceptions.ConnectTimeout:
            self.online_status = False
            self.lock.release()
            raise Exception(f'No Response from {self.__lasturl}')

        if not 'name' in d:
            self.lock.release()
            raise Exception(f'Aspirations not met. No name in reply from machine.')

        if d['name'] != self.what_i_aspire_to_be:
            self.lock.release()
            raise Exception(f'Aspirations not met. Machine is not "{self.what_i_aspire_to_be}". Got: "{d["name"]}"')

        print(d)
        self.lock.release()
        return self.IP

    def say_hello(self):
        """
        I K40 this looks like it just inits the interface on the machine.
        """
        self.lock.acquire()
        d = dict()
        d['result'] = 'fail'

        try:
            d = self.blast(['/system?action=get_dev_name'])

        except requests.exceptions.ConnectTimeout:
            self.online_status = False
            self.lock.release()
            raise Exception(f'No Response from {self.__lasturl}')

        self.lock.release()
        return d['name'] + " says Hello!"

    def head_position(self, unit):
        if unit == 'mm':
           x = self.__drlocx
           y = self.__yflip * self.__drlocy
        elif unit == 'in':
           x = self.__drlocx / 25.4
           y = self.__yflip * self.__drlocy / 25.4
        else:
           raise Exception("must specify unit, 'mm' or 'in'")
        return (x, y)

    def head_position_units(self):
        return 'mm'


    def get_working_state(self):
        self.blast([f'/system?action=get_working_sta'])
        return self.blast([f'/system?action=get_working_sta'])

    def get_status(self):
        return self.blast([f'/peripherystatus'])

    def print_status(self):
        print(self.blast([f'/peripherystatus']))
    
    def unlock_rail(self):
        print("unlock rail")
        s = ['/cmd?cmd=M18']
        self.blast(s)

    def e_stop(self):
        s = ['/cnc/data?action=stop']
        self.blast(s, expect='fail')

    def home_position(self):
        self.__drlocx = 0
        self.__drlocy = 0
        print("XTool home requested")
        raise Exception("ManualHomeRequest")

    def reset_usb(self):
        print("reset usb")

    def release_usb(self):
        print("releaseusb ")
        self.dev = None
        self.USB_Location = None

    def pause_un_pause(self):
        if self.paused:

            # Restore the machine modal state
            # so it can carry on with more G0, G1
            rapid = self.sendstates[self.sendi][1]
            feed  = self.sendstates[self.sendi][2]
            power = self.sendstates[self.sendi][3]

            s = ['/cmd?cmd=M17 S1',
                 '/cmd?cmd=G90',
                 f'/cmd?cmd=G0 F{rapid}',
                 f'/cmd?cmd=G1 F{feed}',
                 f'/cmd?cmd=G1 S{power}',
                ]
            self.blast(s)

            self.paused = False

            print("un-pauseed")
        else:
            self.paused = True
            print("pauseed")


    def unfreeze(self):
        print("unfreeze")
        
    def blast(self, s, expect='ok', timeout=3):
        d = dict()
        d['result'] = 'failed' 

        if self.online_status == False:
            d['result'] = 'offline' 
            print(f'INFO: Machine is offline. not sending: {s}')
            return d

        for x in s:
            print(x);
            replystr = self._get_request(x, timeout=timeout).decode('utf-8')
            r = json.JSONDecoder().decode(replystr)
            print(replystr)
            print(r)
            d = d | r

            if 'working' in d:
                self.__working = d['working']

            if 'status' in d:
                self.__status = d['status']

            if expect != '?' and d['result'] != expect:
                msg = f"bad result from device: {d}"
                print(msg)
                #raise Exception(msg)

        return d

    def _get_request(self, path, port=None, timeout=3, **kwargs) -> bytes:
        if port is None: port = self.PORT
        url = f'http://{self.IP}:{port}{path}'
        #print('url: ' + url)
        self.__lasturl = url
        result = requests.get(url, timeout=timeout, **kwargs)
        if result.status_code != 200:
            print('status: ' + str(result.status_code))
            #raise RuntimeError(f'Device returned HTTP status {result.status_code} for GET {url}')
        return result.content

    def none_function(self,dummy=None,bgcolor=None):
        #Don't delete this function (used in send_data)
        return False

    def upload_cut_file(self, data, update_gui=None, stop_calc=None, passes=1, preprocess_crc=True, wait_for_laser=False):
        self.upload_file(data,
             update_gui=update_gui,
             stop_calc=stopcalc,
             passes=passes,
             preprocess_crc=preprocess_crc,
             wait_for_laser=wait_for_laser,
             filetype = 'cut'
            )

    def upload_frame_file(self, data, update_gui=None, stop_calc=None, passes=1, preprocess_crc=True, wait_for_laser=False):
        self.upload_file(data,
             update_gui=update_gui,
             stop_calc=stop_calc,
             passes=passes,
             preprocess_crc=preprocess_crc,
             wait_for_laser=wait_for_laser,
             filetype = 'frame'
            )

    def upload_file(self, data, update_gui=None, stop_calc=None, passes=1, preprocess_crc=True, wait_for_laser=False, filetype='cut'):
        if update_gui == None:
            update_gui = self.none_function

        msg = f'Generating gcode'
        update_gui(msg)
        gcode, segtime = self.ecoord_to_gcode(data)

        gc = ''
        for line in gcode:
           gc = gc + line + '\n'

        if self.debug: print(gc)
        self.upload_gc_file(gc,
             update_gui=update_gui,
             stop_calc=stop_calc,
             passes=passes,
             preprocess_crc=preprocess_crc,
             wait_for_laser=wait_for_laser,
             filetype=filetype
            )


    def upload_gc_file(self, gc, update_gui=None, stop_calc=None, passes=1, preprocess_crc=True, wait_for_laser=False, filetype='cut'):
        if update_gui == None:
            update_gui = self.none_function
        if stop_calc == None:
            stop_calc=[]
            stop_calc.append(0)

        xtool_filetype = ''
        if filetype == 'cut':
           xtool_filetype = '1'
        elif filetype == 'frame':
           xtool_filetype = '0'
        else:
           raise Exception(f'Do not know about file type "{filetype}"')

        msg = f'Uploading Data to X-Tool'
        update_gui(msg)

        if self.debug: print(f'upload_gc_file:\n{gc}')
 
        files = {'file': ('tmp.gcode', gc)}
        path = '/cnc/data?filetype=' + xtool_filetype
        url = f'http://{self.IP}:{self.PORT}{path}'
        if self.debug: print(f'upload_gc_file: {url}')
        if self.debug: print(f'upload_gc_file: {files}')

        result = requests.post(url, files=files)
        if self.debug: print(f'upload_gc_file: {result}')

        if self.debug: print(self.get_working_state())
        if self.debug: print(self.get_status())

        if result.status_code == 200:
            print("INFO: upload success!")
            if filetype == 'cut':
                print("INFO: Green led should be on. Press XTool button to cut.")
                msg = f'Uploading Sucsessful. Use the X-Tool button to start the burn.'
            if filetype == 'frame':
                print("INFO: Blue led should be blinking. Press XTool button to frame.")
                msg = f'Uploading Sucsessful. Use the X-Tool button to start the burn.'
            update_gui(msg)
        else:
            msg = f'Upload Failed: {result}'
            update_gui(msg)

        return result



    def send_data(self, data, update_gui=None, stop_calc=None, passes=1, preprocess_crc=True, wait_for_laser=False):
        print("xtool send_data entering")
        self.paused = False;
        self.sendi = 0;

        # stop_calc is list reference
        # If we set stop_calc[0] to True then the GUI can respond when we do
        # If the GUI set it true then we can respond
        # the update_gui() call back, update_gui(messqae, bgcolor='green')

        if stop_calc == None:
            stop_calc=[]
            stop_calc.append(0)

        if update_gui == None:
            update_gui = self.none_function

        NoSleep = WindowsInhibitor()

        gcode, segtime = self.ecoord_to_gcode(data)

        self.sendstates = segtime

        #print(f'send_data: {gcode}')

        # wait for idle
        #while self.state != 0:
        #   self.update_state()

        x0 = self.__drlocx
        y0 = self.__drlocy
        self.mark = time.time()
        estjobtime = 0
        # because we are sending gcode line by line there is no way
        # to emergency stop
        #
        # do get too far ahead
        for i in range(0, len(gcode)):
           self.blast([f'/cmd?cmd={gcode[i]}'])
           estjobtime = estjobtime + segtime[i][0]

           self.sendi = i;

           print(f'{i:5d} of {len(gcode)}    {gcode[i]}')

           elapsed = time.time() - self.mark
           self.get_working_state()
           msg = f'Sending Data to Laser = {100.0 * i / len(gcode):5.1f}%'
           msg = msg + f'  Elapsed:{elapsed:6.1f}sec  machine state:{self.state}'
           update_gui(msg)

           # This is run in the GUI thread
           # stop_calc[0] goes true if the "Stop Laser Jobs" dialog gets an "OK"
           # Activating that dialog is doable because of the update_gui() calls
           # in this loop. So if dialog is open we are waiting for update_gui()
           # to return.
           #
           # If there is somthing important to do to the machine do it in
           # self.pause_un_pause(). GUI calls that before poping the dialog.
           # A G1 move always turns off the laser at the end so nothing to do.
           if stop_calc[0]:
               # user clicked OK on the stop dialog
               update_gui( "Stopping ....", bgcolor = 'pink' )
               self.blast(['/cmd?cmd=G0 X0 Y0'])
               self.blast(['/cmd?cmd=M108'])
               break;

           while time.time() < self.mark + estjobtime:
               #print(f'wait for machine {self.mark + estjobtime - time.time():6.3f} sec before next code')
               time.sleep(0.010)

           self.__drlocx = x0 + segtime[i][4]
           self.__drlocy = y0 + segtime[i][5]

        self.wait_for_laser_to_finish(update_gui, stop_calc)
        self.__drlocx = x0 + segtime[len(gcode)-1][4]
        self.__drlocy = y0 + segtime[len(gcode)-1][5]

        NoSleep.inhibit()

        print("xtool send_data returning")
        return 


    def wait_for_laser_to_finish(self,update_gui=None,stop_calc=None):

        if self.online_status == False:
            elapsed = time.time() - self.mark
            self.mark = 0
            msg = f'Offline Job Finished. Elapsed:{elapsed:6.1f}sec  machine state:{self.state}'
            update_gui(msg)
            return

        FINISHED = False
        while not FINISHED:
            self.update_state()
            if self.state == 0:
                FINISHED = True
                self.mark = 0
                elapsed = time.time() - self.mark
                msg = f'Job Finished. Elapsed:{elapsed:6.1f}sec  machine state:{self.state}'
                update_gui(msg)
                return
            else: 
                elapsed = time.time() - self.mark
                msg = f'Waiting for laser to finish. Elapsed:{elapsed:6.1f}sec  machine state:{self.state}'
                update_gui(msg)

            if stop_calc[0]:
                update_gui("Stopping ....", bgcolor = 'pink' )
                self.e_stop()
                self.update_state()
                self.mark = 0
                return

            time.sleep(1)
            print(msg)

        return


    def update_state(self):
        d = self.get_working_state()

        if d['result'] == 'ok':
            self.state = int(d['working'])   # 0, 1, 2

        else:
            print(f'WARN unhandled working value in get_state(): {d}')


    def rapid_move(self, dxmils, dymils):
        self.lock.acquire()
        if self.debug: print(f'xtool_lib: rapid_move: dx:{dxmils} mils  dy:{dymils} mils')
        x0 = self.__drlocx
        y0 = self.__drlocy

        xloc = dxmils * 0.0254     # mm
        yloc = -dymils * 0.0254    # mm
        feed = 3000                # mm/min
        # This sequence finishes with gcode abort M108
        # Leave this out and XTool will progress to a timeout, blink red, then green
        # During a long rapid led will transition to blinking blue
        # after the M108 it will go solid green
        s = [
             '/cmd?cmd=M17+S1',
             '/cmd?cmd=G92X0Y0',
             '/cmd?cmd=G90',
             '/cmd?cmd=G1X' + str(xloc) + 'Y' + str(yloc) + 'F' + str(feed) + 'S0',
             '/cmd?cmd=M108'
            ]
        self.blast(s)
        self.mark = time.time()

        # time estimate, sec = length / (3000 mm/min) * 60 sec/min
        estjobtime = math.sqrt(xloc * xloc + yloc * yloc) / feed * 60
        if self.debug: print(f'rapid time = {estjobtime:.2f} sec')

        if estjobtime > 0.010:
            elapsed = (time.time() - self.mark) / estjobtime
            while elapsed < 1.2:
                self.__drlocx = x0 + xloc * elapsed
                self.__drlocy = y0 + yloc * elapsed
                #print(f'wait for machine {self.mark + estjobtime - time.time():6.3f} sec before next code')
                #print(f'{self.get_status()} {self.get_working_state()}')
                self.get_working_state()
                if self.__working == '0':
                    break
                time.sleep(0.010)
                elapsed = (time.time() - self.mark) / estjobtime
        else:
            self.get_working_state()
            while self.__working != '0':
                self.get_working_state()

        self.__drlocx = x0 + xloc
        self.__drlocy = y0 + yloc

        self.lock.release()
        return 

    def ecoord_to_gcode(self, data):
         gcode=[]
         segtime=[]
         scale = 25.4
         # y coords are pre flipped by flag self.flipy
         # units are inch
         # feeds are mm/sec

         #print(f'ecoord_to_gcode: data={data}')

         feed = data[1][3] * 60   # mm/min
         rapid = self.linear_rapid * 60
         power = data[1][4] * self.spindle_power_scale * self.safety_power_scale

         dt = 0
         gcode.append(f'M17 S1')
         gcode.append(f'M205 X426 Y403')  # file uploads do not work with out this
         gcode.append(f'M101')
         gcode.append(f'G90')
         gcode.append(f'G92 X0 Y0')
         gcode.append(f'G0 F{rapid}')
         gcode.append(f'G1 F{feed}')
         gcode.append(f'G1 S{power}')

         if self.safety_power_scale == 0:
            gcode.append(f'M106 S1')    # led cross on
            #gcode.append(f'G92 X17 Y1 (laser offset from led)')

         lastloop = -1
         current_feed = feed
         current_power = power

         lastx = 0
         lasty = 0

         ledon = False

         for i in range(len(gcode)):
            segtime.append([dt, rapid, feed, power, 0, 0])

         for i in range(0,len(data)):
              x = data[i][0] * scale
              y = data[i][1] * scale
              loop = data[i][2]
              feed = data[i][3] * 60    # mm/min
              power = data[i][4] * self.spindle_power_scale * self.safety_power_scale

              dx = x - lastx
              dy = y - lasty
              dist = math.sqrt(dx*dx + dy*dy)
              lastx = x
              lasty = y

              if loop != lastloop:
                  # rapid
                  if self.safety_power_scale == 0 and ledon:
                     gcode.append(f'M106 S0')    # led cross off
                     ledon = False

                  gcode.append(f'G0 X{x:0.3f} Y{y:0.3f}')
                  dt = dist / rapid * 60  # sec
                  segtime.append([dt, rapid, current_feed, current_power, x, y])

              else:
                  # cut
                  if self.safety_power_scale == 0 and not ledon:
                     gcode.append(f'M106 S1')    # led cross on
                     segtime.append(0)
                     ledon = True

                  gc = f'G1 X{x:0.3f} Y{y:0.3f}'

                  if feed != current_feed:
                     gc = gc + f' F{feed:.0f}'
                     current_feed = feed

                  if power != current_power:
                     gc = gc + f' S{power:.0f}'
                     current_power = power

                  gcode.append(f'G1 X{x:0.3f} Y{y:0.3f}')
                  dt = dist / current_feed * 60  # sec
                  segtime.append([dt, rapid, current_feed, current_power, x, y])

              lastloop = loop

         x = 0
         y = 0
         dx = x - lastx
         dy = y - lasty
         dist = math.sqrt(dx*dx + dy*dy)
         dt = dist / rapid * 60  # sec
         gcode.append(f'G0 X{x:0.3f} Y{y:0.3f}')
         segtime.append([dt, rapid, current_feed, current_power, x, y])

         gcode.append(f'M18')
         segtime.append([0, 0, 0, 0, 0, 0])

         if self.safety_power_scale == 0:
            gcode.append(f'M106 S0')    # led cross off
            segtime.append([0, 0, 0, 0])
            #gcode.append(f'G92 X0 Y0')

         tot = 0
         for i in range(0,len(gcode)):
              #print(f'{segtime[i][0]:5.3f} sec  {gcode[i]}')
              tot = tot + segtime[i][0]

         print(f'Total Time Est: {tot:0.1f} sec')

         return gcode, segtime

    def upload_safe_file(self, update_gui=None, stop_calc=None, passes=1, preprocess_crc=True, wait_for_laser=False):
        xsize = 10   # mm
        ysize = 10   # mm
        feed = 1000  # mm/min
        power = 0    # 1000 = 100%
        cross = 0

        x1 = 0
        x2 = x1 + xsize
        y1 = 0
        y2 = y1 + ysize

        gc =  "M17 S1\n"
        gc += f"M106 S{cross}\n"
        gc += "M205 X426 Y403\n"
        gc += "M101\n"

        # laser offset from led cross
        gc += "G92 X17 Y1\n"
        #gc += "G92 X0 Y0\n"

        gc += "G90\n"
        gc += f"G1 F{feed}\n"
        gc += "G0 F3000\n"
        gc += f"G1 S{power}\n"

        gc += f"G0 X{x1} Y{y1}\n"
        gc += f"G1 X{x2} Y{y1}\n"
        gc += f"G1 X{x2} Y{y2}\n"
        gc += f"G1 X{x1} Y{y2}\n"
        gc += f"G1 X{x1} Y{y1}\n"

        #gc += "G0 X0 Y0\n"
        # put led cross on 0,0
        gc += "G0 X17 Y1\n"

        gc += "M18\n"

        self.upload_gc_file(gc, update_gui, stop_calc, passes, preprocess_crc, wait_for_laser, filetype='cut')

        self.upload_gc_file(gc, update_gui, stop_calc, passes, preprocess_crc, wait_for_laser, filetype='frame')

        self.blast({'/cmd?cmd=M108',});

        for i in range(1):
            time.sleep(0.30)
            print(f'{self.get_status()} {self.get_working_state()}')


if __name__ == "__main__":

    xtool = xtool_CLASS()
    run_laser = False

    LOCATION = xtool.initialize_device(verbose=False)
    print('initialize with location=',LOCATION)
    xtool.initialize_device(LOCATION, verbose=False)

    #xtool.q.put(Xmsg(0, ("exit",)))
    #xtool.worker.join()
    #print("all done")
    #exit(0)

    #print('hello', xtool.say_hello())
    print(xtool.unlock_rail())

    xtool.q.put(Xmsg(9, ("print_status",)))
    xtool.q.put(Xmsg(9, ("print_status")))
    #xtool.q.put(Xmsg(9, ("print_status()")))
    #xtool.q.put(Xmsg(9, ("print_status")))

    print("Press Ctrl-C to stop XTool thread")
    stop = False
    try:
        while True:
           if stop: break
    except KeyboardInterrupt:
        stop = True
        xtool.q.put(Xmsg(0, ("exit",)))

    if stop:
        print("XTool worker stoped by user")

    print("wait for XTool thread to finish")
    xtool.worker.join()
    print("all done")
    exit(0)
