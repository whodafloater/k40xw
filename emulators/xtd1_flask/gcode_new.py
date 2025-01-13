#!/usr/bin/env python3
# original code from https://github.com/fritzw/xtm1_toolkit/blob/main/gcode.py
# MIT license

from io import UnsupportedOperation
import math
import re
from textwrap import dedent

import path
from typing import NamedTuple
import re


# This is what gawks patsplit() does
# from https://docs.python.org/3/library/re.html#writing-a-tokenizer

class Token(NamedTuple):
    type: str
    value: str
    line: int
    column: int

def tokenize(code):
    lettercode = 'ABCDFGHIJKLMNPQRSXYZ'
    keywords = []
    for kw in lettercode:
       keywords.append(kw)
    print(keywords)

    builtins = {'ACOS', 'ASIN', 'ATAN', 'COS', 'SIN', 'TAN',
                'ABS', 'EXP', 'FIX', 'FUP', 'LN', 'ROUND', 'SQRT',
                'MOD'
               }

    token_specification = [
        ('NUMBER',   r'\d+(\.\d*)?'),  # Integer or decimal number
        ('ASSIGN',   r'='),            # Assignment operator
        ('END',      r';'),            # Statement terminator
        ('MARK',     r'%\n'),          # Statement terminator
        ('MARKEND',  r'%$'),           # Statement terminator
        ('COMMENT1', r'%[^\n]+\n'),    # %comment
        ('COMMENT2', r'[(][^)]*[)]'),  # (comment)
        ('ID',       r'[A-Za-z]+'),    # Identifiers
        ('OP',       r'[+\-*/]'),      # Arithmetic operators
        ('NEWLINE',  r'\n'),           # Line endings
        ('SKIP',     r'[ \t]+'),       # Skip over spaces and tabs
        ('BO',       r'[[]'),          # expression
        ('BC',       r'[]]'),          # expression
        ('POINTER',  r'#'),            # pointer
        ('MISMATCH', r'.'),            # Any other character
    ]
    tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in token_specification)
    line_num = 1
    line_start = 0
    for mo in re.finditer(tok_regex, code):
        kind = mo.lastgroup
        value = mo.group()
        column = mo.start() - line_start
        if kind == 'NUMBER':
            value = float(value) if '.' in value else int(value)
        elif kind == 'ID' and value in keywords:
            kind = 'word'
        elif kind == 'ID' and value in builtins:
            kind = 'builtin'
        elif kind == 'NEWLINE':
            line_start = mo.end()
            line_num += 1
            continue
        elif kind == 'MARK':
            line_start = mo.end()
            line_num += 1
        elif kind == 'COMMENT1':
            line_start = mo.end()
            line_num += 1
            continue
        elif kind == 'SKIP':
            continue
        elif kind == 'MISMATCH':
            raise RuntimeError(f'{value!r} unexpected on line {line_num}')
        yield Token(kind, value, line_num, column)

    return


class Gcode():
#class GcodeFramer():
    'Analyzes G-code files to determine the area in which the laser is active.'
    def __init__(self) -> None:
        #self.scale = 0
        self.warn = []

        self.is_relative_mode = False
        self.current_command = b''
        self.X = 0
        self.Y = 0
        self.Z = 0
        self.Xminmax = (1e10, -1e10)
        self.Yminmax = (1e10, -1e10)
        self.S = 0
        self.allowed_gcodes = (b'G0', b'G1', b'G00', b'G01',)
        self.cutting_gcodes = (b'G1', b'G01')
        self.disallowed_gcodes = (b'G2', b'G3', b'G02', b'G03')
        self.regex = re.compile(rb'(X|Y)([-0-9\.]+)')
        self.S_regex = re.compile(rb'S([-0-9\.]*)')
        self.starts_cutting = False
        self.is_cutting = False

        self.paths = list()

    def handle_local_gcode(self, match) -> str:
        letter = match.group(1)
        value = float(match.group(2))
        if letter == b'X':
            self.X += value
            if self.is_cutting: self.update_X(self.X)
        elif letter == b'Y':
            self.Y += value
            if self.is_cutting: self.update_Y(self.Y)

    @staticmethod
    def min_max(old_minmax, new_value):
        oldmin, oldmax = old_minmax
        return min(oldmin, new_value), max(oldmax, new_value)

    def update_X(self, value):
        self.Xminmax = self.min_max(self.Xminmax, value)

    def update_Y(self, value):
        self.Yminmax = self.min_max(self.Yminmax, value)

    def handle_global_gcode(self, match) -> None:
        letter = match.group(1)
        value = float(match.group(2))
        if letter == b'X':
            self.X = value
            if self.is_cutting: self.update_X(self.X)
        elif letter == b'Y':
            self.Y = value
            if self.is_cutting: self.update_Y(self.Y)

    def process_line(self, line: bytes) -> None:
        #code = line.split(b';')[0] # Remove comments starting with ;
        #code = code.split(b'#')[0] # Remove comments starting with #
        #print("pl1: line", line)
        #print("pl1: code", code)
        #print("pl1: str", str(code))
        #if len(code.strip()) == 0:
        #    return
        #if b'G91' in code:
        #    self.is_relative_mode = True
        #    return
        #if b'G90' in code:
        #    self.is_relative_mode = False
        #    return 


        # Expressions are delimited with [] and the unary function names
        # Binary math operators:  + - * / OR XOR AND MOD **
        # precedence:  **
        #              * / MOD
        #              + - OR XOR AND
        #
        # Unary operators: ABS, EXP, FIX, FUP, LN, ROUND, SQRT
        #                  ACOS, ASIN, ATAN, COS, SIN, TAN,
        #    FIX rounds left, FUP rounds right
        #    FIX[-2.3] -> -3  FUP[-2.3] -> -2
        #
        # Parameters:  #nnnn=real   where nnnn is 1 through 5999
        #    Parameter eval occurs after a line is parsed
        #    For example, this G move will use an old value of #3
        #    #3=15 G1 X#3
        #
        # comments are delimited by ()
        #    (MSG foobar)   'foobar' is output to a display
        #
        # The modal groups for G codes are:
        # group 1 = {G0, G1, G2, G3, G38.2, G80, G81, G82, G83, G84, G85, G86, G87, G88, G89} motion
        # group 2 = {G17, G18, G19} plane selection
        # group 3 = {G90, G91} distance mode
        # group 5 = {G93, G94} feed rate mode
        # group 6 = {G20, G21} units
        # group 7 = {G40, G41, G42} cutter radius compensation
        # group 8 = {G43, G49} tool length offset
        # group 10 = {G98, G99} return mode in canned cycles
        # group 12 = {G54, G55, G56, G57, G58, G59, G59.1, G59.2, G59.3} coordinate system selection
        # group 13 = {G61, G61.1, G64} path control mode
        # The modal groups for M codes are:
        # group 4 = {M0, M1, M2, M30, M60} stopping
        # group 6 = {M6} tool change
        # group 7 = {M3, M4, M5} spindle turning
        # group 8 = {M7, M8, M9} coolant (special case: M7 and M8 may be active at the same time)
        # group 9 = {M48, M49} enable/disable feed and speed override switches
        # In addition to the above modal groups, there is a group for non-modal G codes:
        # group 0 = {G4, G10, G28, G30, G53, G92, G92.1, G92.2, G92.3}

        self.lineno += 1
        lettercodes = 'MGXYFS'
        func = None
        com = dict()

        com['line'] = line
        com['lineno'] = self.lineno

        code = line.decode(encoding='utf-8')

        # pull out paren delimited comments. only keep the last one
        code = re.split('[()]', code)

        print(len(code), code);
        if len(code) > 1:
           com['comment'] = code[-1]

        code = code[0].upper()

        print('\n----', code)
        code = re.sub('[MGXYFS]', ' \g<0> ', code) # space around commands
        code = re.sub('[ \t]+', ' ', code)         # just one space
        code = code.strip().upper().split()

        # now have something like this:
        #   code = ['G', '1', 'X', '75.03', 'Y', '53.92']

        print('----', code)
        # look for '%' start and stop markers
        if len(code) == 1 and code[0] == '%':
           if self.markstart == None:
               self.markstart = self.lineno
           else:
               self.markstop = self.lineno
           return

        if code[0] == '%':
           com['command'] = 'comment'
           return

        if len(code) >= 2:
           letter = code.pop(0)
           if not letter in lettercodes:
               raise Exception(f"Expected a letter code in {str(lettercodes)}. Got {letter}")
           value = code.pop(0)

           if func == None:
               try:
                   func = getattr(self, f'_Gcode__{letter}{value}')
               except AttributeError:
                   print(f' not implemented: {letter}{value}')
                   func = getattr(self, '_Gcode__not_implemented')

           com[letter] = value

        func(com)
        return


    def parse_gcode(self, gcode: bytes):
        self.lineno = 0
        self.markstart = None
        self.markstop = None

        for line in gcode.split(b'\n'):
            #print(line)
            self.process_line(line)
            if self.markstop:
                break

        if self.markstart != None and self.markstop == None:
            self.warn.append(f"Found a start marker at line {self.markstart} but no stop marker")

        print(self.Xminmax, self.Yminmax)
        self.print_warn()

    def print_warn(self):
        for i in self.warn:
            print(f'WARN: {i}')

    
    def __not_implemented(self, com):
        self.warn.append(f'Gcode not implemented: lineno:{com["lineno"]} line:{com["line"]}')

    def __G0(self, com):
        self.motion = 'rapid'

    def __G1(self, com):
        print(com)

    def __G2(self, com):
        print(com)

    def __G3(self, com):
        print(com)

    def __G21(self, com):
        print(com)

    def __G90(self, com):
        print(com)
        self.is_relative_mode = False

    def __G91(self, com):
        print(com)
        self.is_relative_mode = True

    def __G92(self, com):
        print(com)
        
    def __M1(self, com):
        print(com)
        
    def __M2(self, com):
        print(com)
        return 'end'
        
    def __M30(self, com):
        print(com)
        return 'end'
        
    def __M17(self, com):
        print(com)
        
    def __M18(self, com):
        print(com)

    def __M101(self, com):
        print(com)
        
    def __M106(self, com):
        print(com)
        
    def __M205(self, com):
        print(com)


    def calculate_frame(self, gcode: bytes):
        for line in gcode.split(b'\n'):
            self.process_line(line)
        print(self.Xminmax, self.Yminmax)

    def calculate_frame_file(self, filename: str):
        with open(filename, 'rb') as f:
            for line in f.readlines():
                self.process_line(line)




if __name__ == '__main__':

    #import gcode_samples

    samples = [
               gcode_samples.gc1,
#               gcode_samples.gc2,
#               gcode_samples.gc_hello_world,
#               gcode_samples.gc_expression_test
              ]

    for gc in samples:
        print(gc.decode(encoding='utf-8').upper())

        for token in tokenize(gc.decode(encoding='utf-8').upper()):
            print(f'  {token.line:4d}  {token.type:20s}  {token.value}')

    #gcode = Gcode()
    #gcode.parse_gcode(gc1)
    #gcode.parse_gcode(gc2)
    #gcode.parse_gcode(gc3)

    #for p in gcode.paths:
    #    print(p)

