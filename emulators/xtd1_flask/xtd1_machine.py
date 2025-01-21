#!/usr/bin/env python3

import sys
if __name__ == '__main__':
    sys.path.append("../..")
    sys.path.append("../../src")
    print("sys.path =", sys.path)

import argparse
import textwrap
import threading
import queue
from dataclasses import dataclass, field
from typing import Any

#import os, signal

import tkinter as tk
#from tkinter import tk
from tkinter import ttk
import emulators.tklib.tklib as tklib

from flask import Flask
from flask import url_for
from flask import request
from urllib.parse import urlparse

import plotter

flapp = Flask(__name__)

@dataclass(order=True)
class Xmsg:
    priority: int
    item: Any=field(compare=False)


class Machine:
    def __init__(self, nogui=False, host=None, port=None, debug=False, *args, **kwargs):

        # LED slow blinking blue    working on GCODE.
        # LED fast blinking red     was working, timeed out waiting for gcode, then transition to state 0
        # LED solid green           working state = 0 

        print(args)
        print(kwargs)

        self.flapp_args = dict()
        self.flapp_args['host'] = host
        self.flapp_args['port'] = port

        if debug and nogui:
            self.flapp_args['debug'] = debug
            

        tklib.App.debug = debug

        print(self.flapp_args)
 
        self.nogui = nogui
        if True or not nogui:
            # need this before doing any tk stuff
            self.app = None
            self.app = tklib.App('Machine Emulator')
            #self.app.root.add_statusbar()

            #top = self.app.root.winfo_toplevel()
            #top = self.app.root
            #top.geometry("300x600")
            assert(tklib.App.win == self.app.root)
            assert(tklib.App.win == self.app.root.winfo_toplevel())

            self.tickstr = tk.StringVar()
            self.tmpGcode = tk.StringVar()

            self.create_pack()
            self.tcount = tk.IntVar()
            self.tcount.set(0)
            self.tick()
            #tklib.get_widget_attributes(self.app.root)

            if debug:
               self.log.insert('end', 'INFO: Flask server debug was disabled because it is run in a thread\n')
               self.log.insert('end', 'INFO: To debug the server, start with: -d --nogui\n')

        self.name = 'xTool D1'
        self.sn   = 'MD1220907E502E9B30'
        self.version   = 'V40.30.010.01 B2'
        self.mac = "B8:D6:1A:35:3B:70"
        self.laserpowertype = 10

        self.working = 0
        self.status = 'normal'
        self.sdcard = 1
        self.offset = [0,0]
        self.dotMode = 1


        self.tmp_gcode = []
        self.tmp_cmd = []

        self.q = queue.PriorityQueue()
        self.lock = threading.Lock()
        self.lock.acquire()
        self.lock.release()


    def que(self, command):
        self.q.put(Xmsg(0, command))
 

    def tick(self):
        self.app.root.after(1000, self.tick)
        self.tcount.set((self.tcount.get()+1))
        self.tickstr.set(f'tick:{self.tcount.get()}')

        #print(f'tick:{self.tcount.get()}')
        #self.log.insert('end', f'tick:{self.tcount.get()}\n')
        self.tick_annuciator.configure(background='light green')
        

    def create_pack(self):
        #tklib.Label().pack_configure(fill='x')
        #sep1 = tklib.Separator()

        #tklib.Frame().pack_configure(fill='both', expand=True)

        # main frame with the plot window gets to expand
        #tklib.Frame().pack_configure(fill='both', expand=True)
        main = tklib.PanedWindow(name='main', orient='horizontal')

        tklib.Frame(name='codeview', weight=30)
        if True:
            # gcode window
            tklib.Frame().pack_configure(side='left', fill='both', expand=True)
            #tklib.Frame().grid(row=0, column=0)
            tklib.Label(text='tmp.gcode')
            self.gcode_viewer = tklib.Text(text='', scroll='xy', width=20, height=1)
            #self.gcode_viewer.pack_configure(fill='y', expand=True)
            self.gcode_viewer.grid_configure(sticky='nsew')
            self.app.stack.pop()
            tklib.Pop()

        machine = tklib.Frame(name='machine', weight=70)
        tklib.PanedWindow(orient='vertical')

        plat = tklib.Frame(name='plat')

        if True:
            # status panel
            s =tklib.Frame(weight=25).pack_configure(side='right', expand=False, fill='y')
            tklib.LabelFrame(text='status', padding=2)

            #tklib.Frame().grid(row=0, column=2)
            #tklib.Label()
            self.tick_annuciator = tklib.Label(text='stopped', background='pink', textvariable=self.tickstr)

            tklib.Pop()
            tklib.Pop(s)

        if True:
            # plot window
            s =tklib.Frame(weight=75).pack_configure(anchor='center', expand=True, fill='both')
            #tklib.Frame().grid(row=0, column=1)
            #bed = tklib.Canvas(bg='light blue')
            bed = plotter.Plotter(enable_sketcher=False, width=500, height=500)
            bed.pack_configure(expand=True, fill='both')

            tklib.Pop(s)

        tklib.Pop()
        tklib.Pop(plat)  # called with param to verify we know where we are

        #self.app.stack.pop()
        #tklib.Separator()

        # log output frame, no expansion. vertical size is
        # set by the text widget height (number of lines)
        lf = tklib.Frame()
        #lf = pack_configure(side='bottom', expand=False, fill='x')
        self.log = tklib.Text(text='INfO: gui says "hello"\n', scroll='xy', height=6, width=1)
        self.log.grid_columnconfigure(0, weight=1)
        self.log.grid_configure(sticky='nsew')

        tklib.Pop()
        tklib.Pop()
        tklib.Pop(machine)
        tklib.Pop(main)

        if False:
            l =ttk.Label(tklib.App.stack[-1], text="Starting...")
            l.pack()
            l.bind('<Enter>', lambda e: l.configure(text='Moved mouse inside'))
            l.bind('<Leave>', lambda e: l.configure(text='Moved mouse outside'))
            l.bind('<ButtonPress-1>', lambda e: l.configure(text='Clicked left mouse button'))
            l.bind('<3>', lambda e: l.configure(text='Clicked right mouse button'))
            l.bind('<Double-1>', lambda e: l.configure(text='Double clicked'))
            l.bind('<B3-Motion>', lambda e: l.configure(text='right button drag to %d,%d' % (e.x, e.y)))

    def new_cmd(self, *args, **kwargs):
        if self.nogui: return
        self.log.insert('end', f'tick:{self.tcount.get()}: cmd, {self.tmp_cmd[0]}\n')

    def new_gcode(self, *args, **kwargs):
        if self.nogui: return
        self.log.insert('end', f'tick:{self.tcount.get()}: gcode upload, {len(self.tmp_gcode)} lines\n')
        self.tmpGcode.set("".join(self.tmp_gcode))
        #  '0.0' is line 0, column 0
        self.gcode_viewer.delete('0.0', 'end')
        self.gcode_viewer.insert('end', self.tmpGcode.get())

    def worker(self):
        #   Xmsg(priority, message)
        #   message must be a tuple
        #   self.q.put(Xmsg(0, ("exit")))
        #   self.q.put(Xmsg(0, ("junk", 'hello', 'bye', 3.14)))
        #   self.q.put(Xmsg(2, ("abort", 'hello', 'timeout:4.5', 'name=foo')))
        #   self.q.put(Xmsg(2, ("abort", 'hello', '{timeout:4.5, name:foo}')))
        #   self.q.put(Xmsg(2, ("get_status",)))
        #   self.q.put(Xmsg(9, ("rapid_move", 1000, 1000)))
        #   self.q.put(Xmsg(2, ("get_status",)))
        #   self.q.put( Xmsg(9, ("rapid_move(1000, 1000)",) ))
        #   self.q.put( Xmsg(9, "rapid_move(1000, 1000)" ) )
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
                continue

            if command == 'kill':
                break;

            for n in itemargs:
                if ':' in str(n):
                     f = re.split(r'[() \t:{}]+', n)
                     if f[0] == '': f.pop(0)
                     while len(f) > 1:
                        key = f.pop(0)
                        val = f.pop(0)
                        kwargs[key]=val
                else:
                     args.append(n)

            print(f'    command: {command:20s} {args} {kwargs}')

            if True:
               method = getattr(self, command)
               method(*args, **kwargs)
            else:
                try: 
                    method = getattr(self, command)
                    method(*args, **kwargs)
                except AttributeError:
                    raise Exception(f' not implemented: {command}')

            self.q.task_done()
        return 

    def server(self):
        global flapp
        print("starting server")
        flapp.run(**self.flapp_args)

    def run(self):
        self.worker = threading.Thread(target=self.worker, daemon=True)
        self.worker.start()

        if self.nogui:
           self.server()  # blocks,  ctrl-c to stop it

        if not self.nogui:
           self.server = threading.Thread(target=self.server, daemon=True)
           self.server.start()
           self.app.run()       # blocks, runs tk mainloop, must be called from main thread
           print('app finshed')


        self.q.put(Xmsg(0, ("exit")))
        self.worker.join()

        # there is no thread shutdown() method. 
        try:
            self.server.shutdown()
        except AttributeError as e:
            print(e)
            print('Flask server shutdown ...')
            print('machine finshed')
            # flask thread dies with exit
            exit(0)

        # never reached, prempted above
        # self.server.join()
        print('machine finshed')
        return


@flapp.route("/")
def hello():
    global machine
    if machine == None:
        machine = xtd1_machine.Machine(nogui=True)
       
    d = dict()
    d['result'] = 'no file'
    return d


@flapp.route("/system")
def system(*args, **kwargs):
    global machine
    print("system")

    action = request.args.get('action')
    print(f'action={action}')

    d = dict()
    d['result'] = 'ok'

    if action == 'get_dev_name':
        d['name'] = machine.name

    elif action == 'version':
        d['sn'] = machine.sn
        d['version'] = machine.version

    elif action == 'mac':
        d['mac'] = machine.mac

    elif action == 'dotMode':
       d['dotMode'] = machine.dotMode

    elif action == 'get_working_sta':
       d['working'] = machine.working

    elif action == 'offset':
       d["x"], d["y"] = machine.offset

    else:
       d['result'] = 'fail'
  
    return d


@flapp.route("/getlaserpowertype")
def getlaserpowertype(*args, **kwargs):
    print("getlaserpowertype")
    d = dict()
    d['power'] = machine.laserpowertype
    d['result'] = 'ok'

    return d

@flapp.route("/cmd")
def cmd(*args, **kwargs):
    print("cmd")

    cmd = request.args.get('cmd')
    print(f'cmd={cmd}')

    machine.tmp_cmd = []
    machine.tmp_cmd.append(str(cmd))
    machine.que(("new_cmd"))

    d = dict()
    d['result'] = 'ok'

    return d

@flapp.route("/progress")
def progress(*args, **kwargs):
    d = dict()

    # cut file progress 
    #   when machine is paused 'working' keeps ticking
    #   when cut file is done,
    #        LED goes grean  remains at 100%,
    #   'line' is gcode line count
    d['result'] = 'ok'
    d['progress'] = 100  # percent done
    d['working'] = 999   
    d['line'] =  19          # gcode line

    return d


@flapp.route("/peripherystatus")
def peripherystatus(*args, **kwargs):
    print("cmd")

    d = dict()
    d['result'] = 'ok'
    d['status'] = 'normal'
    d['sdCard'] = 1
    return d
    #return json.JSONEncoder().encode(d)

@flapp.route("/cnc/data", methods=['GET', 'POST'])
def cnc_data(*args, **kwargs):
    print("cnc/data")

    d = dict()
    d['result'] = 'ok'

    # /cnc/data?action=stop
    if request.method == 'GET':
        action = request.args.get('action')
        print(f'action={action}')
        if action == 'stop':
            print(f'action={action}')
            d['result'] = 'fail'
        else:
            return 404

    if request.method == 'POST':
        filetype = request.args.get('filetype')
        f = request.files['file']

        #print(f'filetype={filetype}')
        #print(f'f={f}')
        #print(f'data: {request.data}')
        #print(f'form: {request.form}')
        #print(f'raw: {request.get_data()}')
        #print(f'raw: {request.get_data().decode("utf-8")}')

        #  https://flask.palletsprojects.com/en/stable/api/#flask.Request.files
        machine.tmp_gcode = []
        for line in f:
            print(f'line: {line.decode("utf-8")}')
            machine.tmp_gcode.append(line.decode('utf-8'))
        machine.que(("new_gcode"))

        if filetype == 0:
            # frame
            machine.working_state = 2

        elif filetype == 1:
            # cut
            machine.working_state = 0

        else:
            d['result'] = 'fail'

    return d

#@flapp.route('/stopServer', methods=['GET'])
#def stopServer():
#    os.kill(os.getpid(), signal.SIGINT)
#    return jsonify({ "success": True, "message": "Server is shutting down..." })


def main():
    global machine

    epilog = textwrap.dedent("""\
        You can also start the server with Flask:
            Flask --app xtd1_flask --host 127.0.0.1 run
            Flask xtd1_flask routes
            Flask --help
        """)

    parser = argparse.ArgumentParser(
       description='X Tool D1 wifi Connection Emulator',
       formatter_class=argparse.RawDescriptionHelpFormatter,
       epilog = epilog
      )

    parser.add_argument('-d', "--debug", required=False, action='store_true',
                        help='Flask debug flag')

    parser.add_argument('-g', "--nogui", required=False, action='store_true',
                        help='no GUI')

    parser.add_argument('-a', "--host", required=False, default='127.0.0.1',
                        help='Emulator IP address')

    parser.add_argument('-p', "--port", required=False, default='8080',
                        help='Emulator port. The real XTool uses port 8080.')

    parser.add_argument('command', choices=['run'])

    argu = parser.parse_args()
    args = vars(argu)

    print(args)

    if argu.command == 'run':
        #del args['command']
        #del args['nogui']

        machine = Machine(**args)
        machine.run()

        #print(f' starting server with {args}')
        #flapp.run(**args)


if __name__ == '__main__':

    main()

    #machine = Machine(nogui=True)

    #t = machine.start()
    #print(t)
    #t.join()

    #machine.run()

    exit(0)
