#!/usr/bin/env python 
'''
X-Tool D1 machine class for K40 Whisperer

Copyright (C) 2024 whodafloater

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
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

##############################################################################

class xtool_CLASS:
    def __init__(self):
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


    def initialize_device(self, Location=None, verbose=False):
        if Location != None:
           self.IP = Location
        return self.IP

    def say_hello(self):
        r = dict()
        r['result'] = 'fail'

        try:
            self.online_status = True
            s = ['/system?action=get_dev_name']
            r = self.blast(s)
            print(f"INFO: Machine is {r}")

        except:
            self.online_status = False
            print("INFO: Machine is offline")

        return r['result']

    def get_working_state(self):
        return self.blast([f'/system?action=get_working_sta'])

    def get_status(self):
        return self.blast([f'/peripherystatus'])
    
    def unlock_rail(self):
        print("unlock rail")
        s = ['/cmd?cmd=M18']
        self.blast(s)

    def e_stop(self):
        s = ['/cnc/data?action=stop']
        self.blast(s, expect='fail')

    def home_position(self):
        print("home")

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
        
    def blast(self, s, expect='ok'):
        d = dict()
        d['result'] = 'failed' 

        if self.online_status == False:
            #print(f'INFO: Machine is offline. not sending: {s}')
            return

        for x in s:
            #print(x);
            replystr = self._get_request(x).decode('utf-8')
            r = json.JSONDecoder().decode(replystr)
            #print(r)
            d = d | r

            if d['result'] != expect:
                msg = f"bad result from device: {d}"
                #raise Exception(msg)

        return d

    def _get_request(self, url, port=None, **kwargs) -> bytes:
        if port is None: port = self.PORT
        full_url = f'http://{self.IP}:{port}{url}'
        #print('url: ' + full_url)
        result = requests.get(full_url, timeout=3, **kwargs)
        if result.status_code != 200:
            print('status: ' + str(result.status_code))
            #raise RuntimeError(f'Device returned HTTP status {result.status_code} for GET {full_url}')
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
        url = '/cnc/data?filetype=' + xtool_filetype
        full_url = f'http://{self.IP}:{self.PORT}{url}'
        if self.debug: print(f'upload_gc_file: {full_url}')
        if self.debug: print(f'upload_gc_file: {files}')

        result = requests.post(full_url, files=files)
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

        self.wait_for_laser_to_finish(update_gui, stop_calc)

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
        if self.debug: print(f'xtool_lib: rapid_move: dx:{dxmils} mils  dy:{dymils} mils')
        xloc = dxmils * 0.0254     # mm
        yloc = -dymils * 0.0254    # mm
        feed = 3000                # mm/min
        # This sequence finishes with gcode abort M108
        # Leave this out and XTool will progress to a timeout, blink red, then green
        # During a long rapid led will transition to blinking blue
        # after the M108 it will go solid green
        s = ['/cmd?cmd=M17+S1',
             '/cmd?cmd=G92X0Y0',
             '/cmd?cmd=G90',
             '/cmd?cmd=G1X' + str(xloc) + 'Y' + str(yloc) + 'F' + str(feed) + 'S0',
             '/cmd?cmd=M108'
            ]
        self.blast(s)

        # time estimate, sec = length / (3000 mm/min) * 60 sec/min
        time_est = math.sqrt(xloc * xloc + yloc * yloc) / feed * 60
        if self.debug: print(f'rapid time = {time_est:.2f} sec')
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
            segtime.append([dt, rapid, feed, power])

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
                  segtime.append([dt, rapid, current_feed, current_power])

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
                  segtime.append([dt, rapid, current_feed, current_power])

              lastloop = loop

         x = 0
         y = 0
         dx = x - lastx
         dy = y - lasty
         dist = math.sqrt(dx*dx + dy*dy)
         dt = dist / rapid * 60  # sec
         gcode.append(f'G0 X{x:0.3f} Y{y:0.3f}')
         segtime.append([dt, rapid, current_feed, current_power])

         gcode.append(f'M18')
         segtime.append([0, 0, 0, 0])

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

    try:
        LOCATION = xtool.initialize_device(verbose=False)
        
    # the following does not work for python 2.5
    except RuntimeError as e: #(RuntimeError, TypeError, NameError, StandardError):
        print(e)    
        print("Exiting...")
        os._exit(0) 
    
    print('initialize with location=',LOCATION)
    xtool.initialize_device(LOCATION, verbose=False)

    print('hello', xtool.say_hello())
    print(xtool.unlock_rail())
    print ("DONE")

    

    
