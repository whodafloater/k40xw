#!/usr/bin/env python3
# 2025 whodafloater
# MIT license

from io import UnsupportedOperation
import math
import re
from textwrap import dedent

import path
from typing import NamedTuple
import re

from enum import Enum

# tokenizer leveraged from the example here
# from https://docs.python.org/3/library/re.html#writing-a-tokenizer

class Token(NamedTuple):
    type: str
    value: str
#    arity: int
#    precedence: int
    lineno: int
    column: int

class Expr(NamedTuple):
    toks: list[Token]

class Assign(NamedTuple):
    name: list[Token]
    expr: Expr


#debug_tok = False
debug_tok = True
 
def gcode_tokenize(code):
    """G-Code tokenizer

       Expressions are delimited with [] and the unary function names
       Binary math operators:  + - * / OR XOR AND MOD **
       precedence:  **
                    * / MOD
                    + - OR XOR AND
       
       Unary operators: ABS, EXP, FIX, FUP, LN, ROUND, SQRT
                        ACOS, ASIN, ATAN, COS, SIN, TAN,
          FIX rounds left, FUP rounds right
          FIX[-2.3] -> -3  FUP[-2.3] -> -2
       
       Parameters:  #nnnn=real   where nnnn is 1 through 5999
          Parameter eval occurs after a line is parsed
          For example, this G move will use an old value of #3
          #3=15 G1 X#3
       
       comments are delimited by ()
          (MSG foobar)   'foobar' is output to a display
    """

    lettercodes = 'ABCDFGHIJKLMPQRSTXYZ'
    keywords = []
    for kw in lettercodes:
        keywords.append(kw)

    # operator and precedence
    binary_op = {'**':3, '*':2, '/':2, 'MOD':2, '+':1, '-':1, 'OR':1, 'XOR':1, 'AND':1}

    # example: ABS [ expr ]
    unary_fn =  ['ABS', 'EXP', 'FIX', 'FUP', 'LN', 'ROUND', 'SQRT',
                 'ACOS', 'ASIN', 'COS', 'SIN', 'TAN']

    binary_fn =  []

    ternary_fn =  ['ATAN']

    arity = dict()
    arity['ATAN'] = [Expr, Token , Expr]
    # example: ATAN [ Y expr ] / [ X expr ]  we accept expr op expr as args

    token_specification = [
        ('NUMBER',   r'\d+(\.\d*)?'),  # Integer or decimal number
        ('LINENO',   r'N\d+'),         # line number 
        ('ASSIGN',   r'='),            # Assignment operator
        ('END',      r';'),            # Statement terminator
        ('MARK',     r'%\n'),          # program start marker
        ('MARKEND',  r'%$'),           # program end marker
        ('COMMENTP', r'%[^\n]+'),      # % comment, do not eat the \n
        ('COMMENT',  r'[(][^)]*[)]'),  # ( comment ), do not eat the \n
        ('ID',       r'[A-Za-z]+'),    # Identifiers
        ('OP',       r'([*][*])|([+\-*/])'),  # Arithmetic operators
        ('NEWLINE',  r'\n'),           # Line endings
        ('SKIP',     r'[ \t]+'),       # Skip over spaces and tabs
        ('BO',       r'\['),           # expression
        ('BC',       r'\]'),           # expression
        ('POINTER',  r'#'),            # pointer
        ('MISMATCH', r'.'),            # Any other character
    ]
    tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in token_specification)
    if debug_tok: print("regex", tok_regex)
    line_num = 1
    line_start = 0
    for mo in re.finditer(tok_regex, code):
        kind = mo.lastgroup
        value = mo.group()
        column = mo.start() - line_start
        precedence = 0
        arity = 0

        if kind == 'NUMBER':
            value = float(value) if '.' in value else int(value)

        elif kind == 'ID' and value in keywords:
            kind = 'word'

        elif kind == 'OP' and value in binary_op:
            precedence = binary_op[value]
            kind = 'binary_op'
            arity = 2

        elif kind == 'ID' and value in binary_op:
            precedence = binary_op[value]
            kind = 'binary_op'
            arity = 2

        elif kind == 'ID' and value in unary_fn:
            kind = 'unary_fn'
            arity = 1

        elif kind == 'ID' and value in binary_fn:
            kind = 'binary_fn'
            arity = 2

        elif kind == 'ID' and value in ternary_fn:
            kind = 'ternary_fn'
            arity = 3

        elif kind == 'NEWLINE':
            line_start = mo.end()
            line_num += 1
            continue

        elif kind == 'MARK':
            line_start = mo.end()
            line_num += 1
            continue

        elif kind == 'SKIP':
            continue

        elif kind == 'MISMATCH':
            raise RuntimeError(f'{value!r} unexpected on line {line_num}')

        if debug_tok: print(f'{"":10s} new token  line:{line_num:4d} col:{column:2d}  {kind:20s}  {value}')
        #yield Token(kind, value, arity, precedence, line_num, column)
        yield Token(kind, value, line_num, column)


class CANON_UNITS(Enum):
    MM = 1
    INCH = 2

class CANON_PLANE(Enum):
    CANON_PLANE_XY = 1
    CANON_PLANE_YZ = 2
    CANON_PLANE_XZ = 3

class CANON_FEED_REFERENCE(Enum):
    CANON_WORKPIECE = 1
    CANON_XYZ = 2

class CANON_MOTION_MODE(Enum):
    CANON_EXACT_STOP = 1
    CANON_EXACT_PATH = 2
    CANON_CONTINUOUS = 3

class CANON_DIRECTION(Enum):
    CANON_STOPPED = 1
    CANON_CLOCKWISE = 2
    CANON_COUNTERCLOCKWISE = 3

class CANON_SPEED_FEED_MODE(Enum):
    CANON_SYNCHED = 1
    CANON_INDEPENDENT = 2

class Gcode():
    ''' A G-Code Parser based on RS274NGC

        reference:
            The NIST RS274NGC Interpreter - Version 3
            Kramer, Proctro, Messina August 17, 2000 
    '''
    def __init__(self, debug=False) -> None:

        self.debug = debug
        s = self
        #self.default_tok = Token('END', 'end', -1, -1, -1, -1)
        self.default_tok = Token('END', 'end', -1, -1)
        s.arity = dict()
        s.arity['binary_op'] = 2
        s.arity['unary_fn'] = 1

        s.precedence = dict()
        s.precedence['**'] = 3
        s.precedence['*'] = 2
        s.precedence['/'] = 2
        s.precedence['MOD'] = 2
        s.precedence['+'] = 1
        s.precedence['-'] = 1
        s.precedence['OR'] = 1
        s.precedence['XOR'] = 1
        s.precedence['AND'] = 1
        s.precedence[']'] = 0   # looks like an operaotr because it follows a value

        s.G_group = dict()
        s.M_group = dict()

        # ection 3.4, table 4
        # The modal groups for G codes are:
        s.G_group['motion'] = (0, 1, 2, 3, 38.2, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89)
        s.G_group['plane_selection'] = (17, 18, 19)
        s.G_group['distance_mode'] = (90, 91)
        s.G_group['feed_rate_mode'] = (93, 94)
        s.G_group['units'] = (20, 21)
        s.G_group['cutter_radius_compensation'] = (40, 41, 42)
        s.G_group['tool_length_offset'] = (43, 49)
        s.G_group['canned_cycle_return_mode'] = (98, 99)
        s.G_group['coordinate_system_selection'] = (54, 55, 56, 57, 58, 59, 59.1, 59.2, 59.3)
        s.G_group['path_control_mode'] = (61, 61.1, 64)
        # In addition to the above modal groups, there is a group for non-modal G codes:
        s.G_group['non_modal'] = (4, 10, 28, 30, 53, 92, 92.1, 92.2, 92.3)

        # The modal groups for M codes are:
        s.M_group['stopping'] = (0, 1, 2, 30, 60)
        s.M_group['tool_change'] = (6)
        s.M_group['spindle_turning'] = (3, 4, 5)
        s.M_group['coolant'] = (7, 8, 9)
        s.M_group['speed_feed_override'] = (48, 49)

        self.warn = []
        self.paths = list()

        self.X = 0
        self.Y = 0
        self.Z = 0
        self.S = 0
        self.F = 0



    def motion_apply(self, codes):
        # Section 3.8, table 8
        # Items are executed in the order shown if they occur on the same line.
        #   1. comment (includes message).
        #   2. set feed rate mode (G93, G94   inverse time or per minute).
        #   3. set feed rate (F).
        #   4. set spindle speed (S).
        #   5. select tool (T).
        #   6. change tool (M6).
        #   7. spindle on or off (M3, M4, M5).
        #   8. coolant on or off (M7, M8, M9).
        #   9. enable or disable overrides (M48, M49).
        #   10. dwell (G4).
        #   11. set active plane (G17, G18, G19).
        #   12. set length units (G20, G21).
        #   13. cutter radius compensation on or off (G40, G41, G42)
        #   14. cutter length compensation on or off (G43, G49)
        #   15. coordinate system selection (G54, G55, G56, G57, G58, G59, G59.1, G59.2, G59.3).
        #   16. set path control mode (G61, G61.1, G64)
        #   17. set distance mode (G90, G91).
        #   18. set retract mode (G98, G99).
        #   19. home (G28, G30) or
        #   change coordinate system data (G10) or
        #   set axis offsets (G92, G92.1, G92.2, G94).
        #   20. perform motion (G0 to G3, G80 to G89), as modified (possibly) by G53.
        #   21. stop (M0, M1, M2, M30, M60).

        # G   Any number of G words but only one from any group
        # M   Zero to four M words but only one from each group
        #     special case: M7 and M8 may be active at the same time
        # Others, only one allowed

        print("motion apply:", codes)

        if 'X' in codes:
           if type(codes['X']) == Expr:
               pass
               #self.expr_eval(e = codes['X'])


    def expr_eval(self, e:Expr = None, i=None):
        if e == None: return 0
        if type(e) != Expr: return e
        if len(e.toks) == 0:
            return 0

        stack = list()
        brain = list()
        s = ''

        if self.debug: print('expr_eval:', Gcode.reconstruct(e))

        if i == None:
            i = 0

        t = e.toks[i]
        if t.type != "BO":
            raise Exception(f'expression eval must start with a "["' + Gcode.where(t))
        bo = 1

        while True:
           # hope that we are done
           if len(stack) == 1 and len(brain) == 0 and i == len(e.toks)-1:
               print("return because were at the end")
               return stack[0], i

           if bo == 0:
               print("return because brackets closed")
               return stack[0], i

           i += 1
           if i > len(e.toks)-1:
               raise Exception(f'bad expression')

           t = e.toks[i]
           #kind, value, prec = t.type, t.value, t.precedence
           kind, value = t.type, t.value
           print("eval: new tok is", kind)

           if kind == 'NUMBER':
               stack.append(value)
           elif kind == 'BO':
               #stack.append(kind)
               bo += 1
           elif kind == 'BC':
               bo -= 1
               #Gcode.show_stack(e, stack, brain)
               #v = stack.pop(0)  # reomce the BO from the bottom
               #Gcode.show_stack(e, stack, brain)
               #if v != 'BO':
               #   raise Exception(f'bracket error in expression at line:{t.lineno} column:{t.column} got {v}')
           elif kind == 'binary_op':
               brain.append(t)
           elif kind == 'unary_fn':
               brain.append(t)
               print(" recurse to eval arg1 ...")
               arg, i = self.expr_eval(e, i+1)
               stack.append(arg)
               kind = 'NUMBER'
           elif kind == 'binary_fn':
               brain.append(t)
               arg, i = self.expr_eval(e, i+1)
               stack.append(arg)
               arg, i = self.expr_eval(e, i+1)
               stack.append(arg)
               kind = 'NUMBER'
           elif kind == 'ternary_fn':
               brain.append(t)
               for argc in range(3):
                  print(f"{'':30s} recurse to eval arg{argc} ...")
                  arg, i = self.expr_eval(e, i+1)
                  stack.append(arg)
                  print(f"{'':30s} return with arg{argc} = {arg}\n  bo={bo} i={i} ntoks={len(e.toks)}\n")
                  Gcode.show_stack(e, stack, brain, i)
               kind = 'NUMBER'
           else:
               raise Exception(f'unknown tok type in expression at line:{t.lineno} column:{t.column} got {kind}')
               brain.append(t)

           # doctor, can we operate?
           if kind != 'NUMBER':
               continue

           while True:
               Gcode.show_stack(e, stack, brain)
               if len(brain) == 0:
                   # doctor cannot be trusted
                   break

               #if len(stack) - bo - brain[-1].arity < 0:
               if len(stack) - self.arity[brain[-1].type] < 0:
                   # not enough numbers on the stack
                   break

               print("at the end?", "stacklen=", len(stack), "i=", i, "ntoks=", len(e.toks), "bo=",bo)
               
               # maybe, if we are at the end
               #print("at the end?", len(stack), brain[-1].arity, len(brain), i)
               #print("at the end?", len(stack) - brain[-1].arity == 0)
               #print("at the end?", len(brain) == 1)
               #print("at the end?", i == len(e.toks) -1)
               #if (len(stack) - brain[-1].arity == 0) and (len(brain) == 1) and (i == len(e.toks)-1):
               if (len(stack) - self.arity[brain[-1].type] == 0) and (len(brain) == 1) and (i == len(e.toks)-1):
                   value = Gcode.stack_op(stack, brain.pop().value)
                   Gcode.show_stack(e, stack, brain)
                   continue

               # brain is not empty. stack has more than arity values.
               #print("   braintop:", brain[-1])
               #print("   next tok:", e.toks[i+1])
               #print(brain[-1].precedence,  ">=", e.toks[i+1].precedence, "?")
               #if brain[-1].precedence >= e.toks[i+1].precedence:
               if not e.toks[i+1].value in self.precedence:
                   print("   following tok is not sticky")
                   value = Gcode.stack_op(stack, brain.pop().value)
                   Gcode.show_stack(e, stack, brain)
                   continue

               if self.precedence[brain[-1].value] >= self.precedence[e.toks[i+1].value]:
                   print("   following is stcky we have more stick")
                   value = Gcode.stack_op(stack, brain.pop().value)
                   Gcode.show_stack(e, stack, brain)
                   continue
               break

           continue
           Gcode.show_stack(e, stack, brain)
           raise Exception(f'should be unreachable. bad doctor. fix your algorithm')
           break

    #staticmethod
    def show_stack(e, stack, brain, i=None):
        print('expr_eval:', Gcode.reconstruct(e))
        print("stack:",  stack)
        for b in brain: print("brain:", b)

    #staticmethod
    def reconstruct(thing):
        s = ''
        if type(thing) == Expr:
            for t in thing.toks:
                s = s + ' ' + str(t.value)
            return s

        elif type(thing) == Assign:
            return reconstruct_code(thing.name) + '=' + reconstruct_code(thing.expr)
        elif type(thing) == int:
            return str(thing)
        elif type(thing) == float:
            return str(thing)
        else:
            raise Exception(f' do not know about thing: {type(thing)}')


    def expr_eval_not(self, state=None, stack=None, toks=None):
        ''' recursive expression evaluator with shared state '''
        if state == None:
            if toks == None or len(toks) == 0:
                return 0

            state = dict()
            state['toki'] = 0
            stack = list()

            return self.expr_eval(state, stack, toks)

        s = ''
        for t in toks:
            type, value, prec = t
            s = s + str(value)
            print(t)
        print(s)


    @staticmethod
    def stack_op(stack, op):
        # atan2 is ternary in the gcode language
        # we get atan2( y, '/', x)
        if op == '+':      stack.append( stack.pop() + stack.pop() )
        elif op == '-':    stack.append( stack.pop(-2) - stack.pop() )
        elif op == '*':    stack.append( stack.pop() * stack.pop() )
        elif op == '/':    stack.append( stack.pop(-2) / stack.pop() )
        elif op == '**':   stack.append( math.pow(stack.pop(-2), stack.pop()) )
        elif op == 'MOD':  stack.append( int(stack.pop(-2)) % int(stack.pop()) )
        elif op == 'OR':   stack.append( bool(stack.pop()) or bool(stack.pop()) )
        elif op == 'AND':  stack.append( bool(stack.pop()) and bool(stack.pop()) )
        elif op == 'XOR':  stack.append( bool(stack.pop()) ^ bool(stack.pop()) )
        elif op == 'SIN':  stack.append( math.sin(stack.pop()*math.pi/180) )
        elif op == 'COS':  stack.append( math.cos(stack.pop()*math.pi/180) )
        elif op == 'TAN':  stack.append( math.tan(stack.pop()*math.pi/180) )
        elif op == 'ASIN': stack.append( math.asin(stack.pop())*180/math.pi )
        elif op == 'ACOS': stack.append( math.acos(stack.pop())*180/math.pi )
        elif op == 'ATAN': 
           x = stack.pop()
           ignore = stack.pop()
           y = stack.pop()
           print("atan" , y, x)
           stack.append( math.atan2(y,x) * 180 / math.pi )
           print("atan" , y, x, '=', stack[-1])
           #stack.append( math.atan2(stack.pop(-3) / stack.pop()) * 180 / math.pi )
        elif op == 'FUP':  stack.append( ceil(stack.pop()) )
        elif op == 'FIX':  stack.append( floor(stack.pop()) )
        elif op == 'ABS':  stack.append( abs(stack.pop()) )
        elif op == 'EXP':  stack.append( math.exp(stack.pop(-2), stack.pop()))
        elif op == 'LN':   stack.append( math.log(stack.pop()))
        elif op == 'SQRT':  stack.append( math.sqrt(stack.pop()) )
        elif op == 'ROUND': stack.append( round(stack.pop()) )
        else: raise Exception(f' do not know about operation: {op}')
        return stack[-1]

    @staticmethod
    def stacktest():
        stack = list()

        stack.append(1)
        stack.append(3)
        stack.append(2)
        #print(stack)
        x = Gcode.stack_op(stack, '*')
        x = Gcode.stack_op(stack, '+')
        #print(stack)
        #print(x)
        assert(x == 7)

        stack.append(2)
        x = Gcode.stack_op(stack, '/')
        #print(x)
        assert(x == 3.5)

        stack.append(3)
        stack.append(2)
        x = Gcode.stack_op(stack, 'MOD')
        assert(x == 1)

        stack.append(-0.499)
        x = Gcode.stack_op(stack, 'ROUND')
        assert(x == 0)
        
        stack.append(-0.501)
        x = Gcode.stack_op(stack, 'ROUND')
        assert(x == -1)
        
        stack.append(2.44)
        x = Gcode.stack_op(stack, 'ROUND')
        assert(x == 2)
        
        stack.append(9.975)
        x = Gcode.stack_op(stack, 'ROUND')
        assert(x == 10)
        

    def program_init(self):
        pass


    def process_tokens(self, tokgen):
        #codes = dict()
        tok = next(tokgen, self.default_tok)
        if tok == self.default_tok:
            return
        if tok.type == 'MARKEND':
            return

        while True:
            lineno = tok.lineno
            codes, tok = self.collect_line(tokgen, tok)
            print(f'line {lineno:4d} {codes}') 

            self.motion_apply(codes)

            if tok.type == 'MARKEND':
               break
            if tok.type == 'END':
               break


    def collect_line(self, tokgen, tok):
        # tok should be first tok of new line
        codes = dict()
        lineno = tok.lineno
        #print("    collect line number", lineno)

        while True:
            # Ken, hope that we are done
            print("top of loop. tok=", tok)
            if tok.lineno != lineno:
                break

            # each branch below should deliver a fresh token here
            # print(f'  {tok.lineno:4d}  {tok.type:20s}  {tok.value}')
            if tok.type == 'word':
                word = tok.value

                tok = next(tokgen, self.default_tok)
                value, tok = self.collect_expression(tokgen, tok)
                #print(f'  {tok.lineno:4d}  {tok.type:20s}  {tok.value}')

                if word in "GM":
                    if not word in codes:
                        codes[word] = list()
                    codes[word].append(value)
                else:
                    if word in codes:
                        self.warn.append(f'line: {lineno}: multiple codes of same type not allowed for {word}')
                    codes[word] = value
                continue

            elif tok.type == 'POINTER':
                value, tok = self.collect_assignment(tokgen, tok)
                print('value=', type(value), value)
                continue

            elif 'COM' in tok.type:
                tok = next(tokgen, self.default_tok)
                continue

            elif tok.type == 'LINENO':
                tok = next(tokgen, self.default_tok)
                continue

            print("bottom of loop. tok=", tok)
            # blame it on the gcode
            raise Exception(f'line:{lineno} column:{tok.column}  invalid syntax {tok.type}, value:{tok.value}')
            # still here? we mssed up
            raise Exception(f'line: {lineno}: unhandled token type, {tok.type}, value:{tok.value}')

        return codes, tok


    def collect_assignment(self, tokgen, tok):
        lineno = tok.lineno
        #print(f'{"":20s} assignment  {tok.lineno:4d}  {tok.type:20s}  {tok.value}')

        if tok.type != 'POINTER':
            raise Exception(f'line: {lineno}: Parser Error. Got here by mstake. token type:{tok.type}, value:{tok.value}')

        # variable access is always indirect.  #address, or ##adress
        name = list()
        name.append(tok)
        while True:
            tok = next(tokgen, self.default_tok)   # should be assigment op
            if tok.type == 'ASSIGN':
                break

            if tok.lineno != lineno:
                raise Exception(f'line: {lineno-1}: found EOL while looking for "=". Got {name}')

            name.append(tok)

        tok = next(tokgen, self.default_tok)   # should be expression
        value, tok = self.collect_expression(tokgen, tok)

        return Assign(name, value), tok


    def collect_expression(self, tokgen, tok):
        # expressions are always bound by [ ]
        # those are not included here ... actually need them for function arg parsing
        lineno = tok.lineno
        #print(f'{"":20s} epression   {tok.lineno:4d}  {tok.type:20s}  {tok.value}')

        if tok.type == 'NUMBER':
            val = tok.value
            tok = next(tokgen, self.default_tok)
            #print(f'{"":20s} epression   {tok.lineno:4d}  {tok.type:20s}  {tok.value}')
            if tok.type == 'word' or tok.lineno != lineno:
                # all good, no expr to parse
                #print(f'{"":20s} epression  retruning a number: {expr}')
                return val, tok

        # collect expr toks in a list. do not include the opening [
        e = list()
        e.append(tok)
        bo = 1
        while True:
            tok = next(tokgen, self.default_tok)
            #print(f'{"":20s} epression   {tok.lineno:4d}  {tok.type:20s}  {tok.value}')

            if tok.type == 'BO':
                bo += 1

            elif tok.type == 'BC':
                bo -= 1
                if bo == 0:
                   e.append(tok)
                   break
                # stiil in the expr 

            elif tok.type == 'word':
                break

            elif 'COM' in tok.type:
                continue

            elif tok.lineno != lineno:
                break

            # still here?
            e.append(tok)

        #  last tok should have been a ]
        if tok.type == 'BC':
            # fresh one for caller
            tok = next(tokgen, self.default_tok)
        else:
            raise Exception(f'expression is missing closing "]":' + Gcode.where(tok))

        # type it for later
        return Expr(e), tok

    @staticmethod
    def where(tok):
        return f'line:{tok.lineno} column:{tok.column} "{tok.value}"'
 

    def parse_expr(self, gcode: bytes):
        " For testing expression parsing"
        # prepend 'X' and wrap in '[ ]' to make this valid gcode
        gcode = b'x[' + gcode + b']'
        gcode = gcode.decode(encoding='utf-8').upper()

        self.warn = []
        tokgen = gcode_tokenize(gcode)
        tok = next(tokgen, self.default_tok)
        codes, tok = self.collect_line(tokgen, tok)
        print(f'line  {codes}') 
        val, i = self.expr_eval(e = codes['X'])
        return float(val)

    def parse_gcode(self, gcode: bytes):
        self.markstart = None
        self.markstop = None
        self.warn = []

        tokgen = gcode_tokenize(gcode.decode(encoding='utf-8').upper())

        self.program_init()
        self.process_tokens(tokgen)

        if self.markstart != None and self.markstop == None:
            self.warn.append(f"Found a start marker at line {self.markstart} but no stop marker")

        self.print_warn()

    def print_warn(self):
        for i in self.warn:
            print(f'WARN: {i}')

    def __not_implemented(self, com):
        self.warn.append(f'Gcode not implemented: lineno:{com["lineno"]} line:{com["line"]}')


    # These are from rs274/NGC page 44 table 9
    # Representation 
    def set_origin_offsets(self, x, y, z, a, b, c):
        pass
    def use_length_units(self, units:CANON_UNITS):
        pass
    # Free Space Motion
    def straight_traverse(self, x, y, z, a, b, c):
        pass
    # Machining Attributes
    def select_plane(self, plane:CANON_PLANE):
        pass
    def set_feed_rate(self, rate):
        pass
    def set_feed_reference(self, reference:CANON_FEED_REFERENCE):
        pass
    def set_motion_control_mode(self, mode:CANON_MOTION_MODE):
        pass
    def start_speed_feed_synch(self):
        pass
    def stop_speed_feed_synch(self):
        pass
    # Machining Functions
    def arc_feed(self, first_end, second_end, first_axis, 
                 second_axis, rotation:int, axis_end_point, a, b, c):
        pass
    def dwell(self, seconds):
        pass
    def straight_feed(self, x, y, z, a, b, c):
        pass
    # Probe Functions
    def straight_probe(self, x, y, z, a, b, c):
        pass
    # Spindle Functions
    def orient_spindle(self, orientation, direction:CANON_DIRECTION):
        pass
    def set_spindle_speed(self, r):
        pass
    def start_spindle_clockwise(self):
        pass
    def start_spindle_counterclockwise(self):
        pass
    def stop_spindle_turning(self):
        pass
    # Tool Functions
    def change_tool(self, slot:int):
        pass
    def select_tool(self, i:int):
        pass
    def use_tool_length_offset(self, offset):
        pass
    # Miscellaneous Functions
    def comment(self, s):
        pass
    def disable_feed_override(self):
        pass
    def disable_speed_override(self):
        pass
    def enable_feed_override(self):
        pass
    def enable_speed_override(self):
        pass
    def flood_off(self):
        pass
    def flood_on(self):
        pass
    def init_canon(self):
        pass
    def message(self, s):
        pass
    def mist_off(self):
        pass
    def mist_on(self):
        pass
    def pallet_shuttle(self):
        pass
    # Program Functions
    def optional_program_stop(self):
        pass
    def program_end(self):
        if self.markstart != None and self.markstop == None:
            self.warn.append(f"Found a start marker at line {self.markstart} but no stop marker")

    def program_stop(self):
        pass


if __name__ == '__main__':

    import gcode_samples

    Gcode.stacktest()

    ep = lambda e: Gcode(debug=False).parse_expr(e)
    close = lambda e, want: (1 - Gcode(debug=False).parse_expr(e) / want) < 1e-6

    assert( ep(b'1') == 1)
    assert( ep(b'1+2') == 3)
    assert( ep(b'[1 + 2 * 3 - 4 / 5]') == 6.2)
    assert( ep(b'15 MOD 4.0') == 3)
    assert( ep(b'0 XOR 0') == 0)
    assert( ep(b'0 XOR 1') == 1)
    assert( ep(b'1 XOR 1') == 0)
 
    assert( close( b'2**3', 8.0 ))
    assert( close( b'sin[30]', 0.5 ))
    assert( close( b'sqrt[3]', 1.732051 ))
    assert( close( b'atan[1.7321][1][1.0]', 60.0 ))
    assert( close( b'atan[1.7321]/[1.0]', 60.0 ))

    exit(0)

    samples = [
               gcode_samples.gc1,
               gcode_samples.gc2,
               gcode_samples.gc_hello_world,
               gcode_samples.gc_expression_test
              ]

    gcode = Gcode()
    for gc in samples:
        print(gc.decode(encoding='utf-8').upper())

        gcode.parse_gcode(gc)
