#!/usr/bin/env python3

import threading
import queue
from dataclasses import dataclass, field
from typing import Any

import os, signal

import tkinter as tk
import tklib
from flask import Flask
from flask import url_for
from flask import request
from urllib.parse import urlparse

import argparse
import textwrap

flapp = Flask(__name__)

@dataclass(order=True)
class Xmsg:
    priority: int
    item: Any=field(compare=False)


class Machine:
    def __init__(self, nogui=False, host=None, port=None, debug=False, *args, **kwargs):

        print(args)
        print(kwargs)

        self.flapp_args = dict()
        self.flapp_args['host'] = host
        self.flapp_args['port'] = port
        self.flapp_args['debug'] = debug

        print(self.flapp_args)
 
        self.nogui = nogui
        if not nogui:
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

            self.create()
            self.tcount = tk.IntVar()
            self.tcount.set(0)
            self.tick()

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

        self.q = queue.PriorityQueue()
        self.lock = threading.Lock()
        self.start()
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
        

    def create(self):
        tklib.Label()
        tklib.Separator()

        tklib.Frame()

        tklib.Frame().grid(row=0, column=0)
        tklib.Label(text='tmp.gcode')
        self.gcode_viewer = tklib.Text(text='', scroll={'y':10})
        self.app.stack.pop()

        tklib.Frame().grid(row=0, column=1)
        bed = tklib.Canvas()
        self.app.stack.pop()

        tklib.Frame().grid(row=0, column=2)
        tklib.Label()
        self.tick_annuciator = tklib.Label(text='stopped', background='pink', textvariable=self.tickstr)
        self.app.stack.pop()

        self.app.stack.pop()

        tklib.Separator()

        tklib.Frame()
        self.log = tklib.Text(text='hello', scroll={'y':10})


    def new_gcode(self, *args, **kwargs):
        self.log.insert('end', f'tick:{self.tcount.get()}: gcode upload, {len(self.tmp_gcode)} lines\n')

        self.tmpGcode.set("".join(self.tmp_gcode))
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

        self.server = threading.Thread(target=self.server, daemon=True)
        self.server.start()

        if not self.nogui:
           self.app.run()
           print('app finshed')


        self.q.put(Xmsg(0, ("exit")))
        self.worker.join()

        self.server.shutdown()
        self.server.join()
        print('machine finshed')

    def start(self):
        # cannot start tk mainloop in a thread
        # tk mainloop 
        #   RuntimeError: Calling Tcl from different apartment
        #self.worker = threading.Thread(target=self.app.run, daemon=True)
        #self.worker.start()
        #return self.worker
        pass


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

@flapp.route('/stopServer', methods=['GET'])
def stopServer():
    os.kill(os.getpid(), signal.SIGINT)
    return jsonify({ "success": True, "message": "Server is shutting down..." })


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
