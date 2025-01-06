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
import json
from urllib.parse import urlparse
import argparse
import textwrap


import xtd1_machine


global machine
machine = xtd1_machine.Machine(nogui=True)



flapp = Flask(__name__)

from xtd1_flask_route import *


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

    parser.add_argument('-a', "--host", required=False, default='127.0.0.1',
                        help='Emulator IP address')

    parser.add_argument('-p', "--port", required=False, default='8080',
                        help='Emulator port. The real XTool uses port 8080.')

    parser.add_argument('command', choices=['run'])

    argu = parser.parse_args()
    args = vars(argu)

    if argu.command == 'run':
        machine = xtd1_machine.Machine(nogui=True)
        del args['command']
        print(f' starting server with {args}')
        flapp.run(**args)


if __name__ == "__main__":
    main()
