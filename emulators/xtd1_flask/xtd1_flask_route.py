#!/usr/bin/env/ python3
# 2025 whidafloater
#
# XTool D1 Simulator
#
#   flask --app xtd1_flask run --port 8080
#   flask --debug --app xtd1_flask run --port 8080
#

from flask import Flask
from flask import url_for
from flask import request
from urllib.parse import urlparse
#

#import xtd1_machine
#machine = xtd1_machine.Machine(nogui=True)
#flapp = Flask(__name__)

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
            print(line)
            machine.tmp_gcode.append(str(line))

        if filetype == 0:
            # frame
            machine.working_state = 2

        elif filetype == 1:
            # cut
            machine.working_state = 0

        else:
            d['result'] = 'fail'


    return d
