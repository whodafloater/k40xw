#!/usr/bin/env python 
'''
This is a base class for machines used by K40_Whisperer

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

import time
from windowsinhibitor import WindowsInhibitor

class MachineBase:
    def __init__(self):

       self.online_status = False

       self.IP = None;
       self.port = 8080

       # usb device 
       self.dev = None;

       # serial port
       self.com = None;

       self.state = 'idle'

       self.dialect = 'ecoord'
       #self.dialect = 'egv'


    def initialize_device(self, Location=None, verbose=False):
        if Location != None:
           self.IP = Location
        return self.IP


    def say_hello(self):

        print('INFO: Machine base class is mocking online')
        self.online_status = True

        return 'ok'

    
    def unlock_rail(self):
        print("INFO: unlock rail")

    def e_stop(self):
        print("INFO: stop")

    def pause_un_pause(self):
        print("INFO: un pause")

    def unfreeze(self):
        print("INFO: unfreeze sent")
        
    def home_position(self):
        print("INFO: home")

    def rapid_move(self,dxmils,dymils):
        print(f'INFO: rapid move: dx:{dxmils} mils  dy:{dymils} mils')
        return


    def reset_usb(self):
        print("INFO: reset")

    def release_usb(self):
        if self.dev != None:
           print("INFO: release")
           self.dev = None
           return 

        
    def none_function(self,dummy=None,bgcolor=None):
        #Don't delete this function (used in send_data)
        return False
    

    # In original K40_Whisper data[] is alread converted to evg
    #
    # Here we get ecoords and a function for converting to out machine desired data type
    # 
    # some choices:
    #    stream actual cutting data egv or gcode
    #    upload a file so the machine can do offline cutting or framing
    #
    # this is a mockup that takes ecoords and chunks them out to nowhere

    #   [x, y, loop, feed, pow]
    def send_data(self, data, update_gui=None, stop_calc=None, passes=1, preprocess_crc=True, wait_for_laser=False):

        self.starttime = time.time()
        self.est_duration = 5

        if stop_calc == None:
            stop_calc=[]
            stop_calc.append(0)

        if update_gui == None:
            update_gui = self.none_function

        NoSleep = WindowsInhibitor()
        NoSleep.inhibit()

        print(f'send_data: {data}')

        packets = []
        packet_cnt = 0

        for p in data:
            packet_cnt = packet_cnt + 1.0
            update_gui( "Sending Data to Laser = %.1f%%" %( 100.0*packet_cnt/len(data) ) )

        self.state = 'working'
        if wait_for_laser:
            self.wait_for_laser_to_finish(update_gui,stop_calc)

        NoSleep.uninhibit()


    def get_state(self):
        # K40 
        #    Ok
        #    BUFFER_FULL
        #    CRC_ERROR
        #    UNKNOWN_2
        #    TASK_COMPLETE
        #    TASK_COMPLETE_M3

        # XTool D1
        #    working   0  idle, green led
        #    working   2  framing, blue led
        #    power     0 to 1000
        #    dotMode   0 or 1  ??

        #if self.state == 'working':
        # print(f'time is {time.time()}  working until: {self.starttime + self.est_duration}')
        if time.time() > self.starttime + self.est_duration:
            self.state = 'finished'

        return self.state

    def wait_for_laser_to_finish(self,update_gui=None,stop_calc=None):

        FINISHED = False 
        while not FINISHED:

            response = self.get_state()

            if response == 'finished':
                FINISHED = True
                break

            elif response == None:
                msg = "Laser stopped responding after operation was complete."
                update_gui(msg)
                FINISHED = True

            else: #assume: response == self.OK:
                msg = "Waiting for the laser to finish."
                update_gui(msg)

            if stop_calc[0]:
                self.stop_sending_data()

    def stop_sending_data(self):
        self.e_stop()
        raise Exception("Action Stopped by User.")



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

    

    
