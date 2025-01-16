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

debug_tok = False
#debug_tok = True

class Token(NamedTuple):
    type: str
    value: str
    lineno: int
    column: int

def tokenstr(t):
    return f'line:{t.lineno:3d} col:{t.column:2d}   {t.type:10s} {str(t.value):10s}'

class Strip(NamedTuple):
    toks: list[Token]

class FuncCall(NamedTuple):
    name: Token
    args: list[Token|Strip]

class Expr(NamedTuple):
    toks: list[Token|FuncCall]

class PtrDeRef(NamedTuple):
    toks: Strip|Expr

class Assign(NamedTuple):
    name: PtrDeRef
    expr: [Expr|Token]

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
        self.default_tok = Token('END', 'end', -1, -1)

        token_info = Gcode.token_info()
        #print("token_info:", token_info)

        
        s.arity = dict()
        s.arity['unary_op'] = 1
        s.arity['binary_op'] = 2
        s.arity['unary_fn'] = 1
        s.arity['binary_fn'] = 2
        s.arity['ternary_fn'] = 3
        s.arity['ATAN'] = [Expr, Token , Expr]
        # example: ATAN [ Y expr ] / [ X expr ]  we accept expr op expr as args

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
        # ']' looks like an operator because it follows a value
        # make it sure does try to bind right
        s.precedence[']'] = -9

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

    #staticmethod
    def token_info():
        "Common launguage definitions useful to the tokenizer and the parser"

        lettercodestr = 'ABCDFGHIJKLMPQRSTXYZ'
        lettercodes = []
        for kw in lettercodestr:
            lettercodes.append(kw)

        binary_op = ['**', '*', '/', 'MOD', '+', '-', 'OR', 'XOR', 'AND']
        unary_fn =  ['ABS', 'EXP', 'FIX', 'FUP', 'LN', 'ROUND', 'SQRT',
                     'ACOS', 'ASIN', 'COS', 'SIN', 'TAN']
        binary_fn =  []
        ternary_fn = ['ATAN']

        funcs = list()
        for w in unary_fn + binary_fn + ternary_fn:
            if re.match(r'[A-Za-z]+', w): funcs.append(w)
        #if debug_tok: print("function words", funcs)

        # Ambiguous funcion call cases
        #   function            ATAN
        #   set A axis offset   ATAN    A = tan()
        # The tokenizer splits  ID when when they match the pattern
        #   [lettercode][funcname]
        # The problems are the inverse sin funcs   
        #
        #    X ATAN   -->  word word unary_fn
        #                  x    A    TAN
        # The parser will have to undo this

        return {'lettercodes' : lettercodes,
                'binary_op' : binary_op,
                'unary_fn' : unary_fn,
                'binary_fn' : binary_fn,
                'ternary_fn' : ternary_fn,
                'funcs' : funcs
               }

    #staticmethod
    def tokenize(code):
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

        token_info = Gcode.token_info()
 
        keywords = token_info['lettercodes']
        funcs = token_info['funcs']
        binary_op = token_info['binary_op']
        unary_fn = token_info['unary_fn']
        binary_fn = token_info['binary_fn']
        ternary_fn = token_info['ternary_fn']

        # Numbers with leading signs?  +3.4 -2.1
        # The tokenizer classifies thes as:  binary_op  NUMBER
        # These are handled in expr_eval() with a
        # binary_op to unary_op replacement when no LHS is detected

        token_specification = [
            ('NUMBER',   r'\d+(\.\d*)?'),  # Integer or decimal number
            ('NUMBER2',  r'\.\d+'),        # leading decimal point number
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
            ('RADIX',    r'\.'),           # decimal point get it own token
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

            if debug_tok: print(f'match: col:{column:2d}    kind:{kind:s}    value:{value}')

            # Letter codes and function names get munged together by the ID
            # match:  X SIN -> XSIN
            # split them apart here and yield the letter token
            #   ATAN -> A TAN         would be legal 
            #   X ATAN  ->  X A TAN   is not
            if kind == 'ID':
                #print("id", value)
                #print("id", value[1:])
                if len(value) > 1 and value[1:] in funcs:
                #if len(value) > 1 and value[1:] in funcs and value[1:] not in nomunge:
                    letter = value[0]
                    func = value[1:]

                    #print("insert a tok")
                    kind = 'word'
                    value = letter
                    if debug_tok: print(f'{"":10s} new token  line:{line_num:4d} col:{column:2d}  {kind:20s}  {value}')
                    #yield Token('word', letter, line_num, column)
                    yield Token(kind, value, line_num, column)

                    kind = 'ID'
                    value = func
                    column += 1
    
            if kind == 'NUMBER' or kind == 'NUMBER2':
                value = float(value) if '.' in value else int(value)

            elif kind == 'ID' and value in keywords:
                kind = 'word'

            elif (kind == 'OP' or kind == 'ID') and value in binary_op:
                kind = 'binary_op'

            elif kind == 'ID' and value in unary_fn:
                kind = 'unary_fn'
 
            elif kind == 'ID' and value in binary_fn:
                kind = 'binary_fn'
  
            elif kind == 'ID' and value in ternary_fn:
                kind = 'ternary_fn'

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
            yield Token(kind, value, line_num, column)


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

        print("motion_apply:")
        if 'F' in codes:
            self.f = self.expr_eval(codes['F'])
            print(f'   F = {self.f}')

        if 'X' in codes:
            self.x = self.expr_eval(codes['X'])
            print(f'   X = {self.x}')


        for c in codes:
            print(c)
            if len(c) > 1:
                for b in c:
                   print("   ", b)

        if 'X' in codes:
           if type(codes['X']) == Expr:
               for c in codes['X']:
                   print(c)
               pass
               #self.expr_eval(e = codes['X'])

    def expr_show(self, e:Expr = None):
        #if e == None: return s + 'None\n'
        #if type(e) != Expr:
        #    return s + 'not an Expr:' + str(e) + '\n'

        #if len(e.toks) == 0:
        #    return s + 'length is 0\n'

        print('\n\n--- expr_show ---')
        #s = Gcode.reconstruct(e)
        #print(s)


        s = Gcode.reconstruct(e)
        print(s)

#        for ts in e:
#            for t in ts:
#                if type(t) == Token:
#                    print(f'{"":4s} line:{t.lineno:4d} col:{t.column:2d} {t.type:20s}  {t.value}')
#                elif type(t) == FuncCall:
#                    print(f'{"":4s} FuncCall  {t.name}')

        print('--- expr_show end---')

        #for t in e:
        #    s = s + '\n' f' {t.type} {t.value} '

        #print(s)

        return


    def expr_eval(self, e:Expr = None, i=None):
        result, i = self._expr_eval(e = e, i = i)
        return result
    
    def _expr_eval(self, e:Expr = None, i=None):

        if self.debug: print('expr_eval:', Gcode.reconstruct(e))
        if e == None: return 0
        
        if type(e) != Expr and type(e) != FuncCall: return e, 0

        #if type(e) == Expr and len(e.toks) == 0:
        #    return 0

        #  a plain FuncCall must be wrapped in [ ]
        if type(e) == FuncCall:
           e = Expr(toks = [
                  Token('BO', '[', 0, 0),
                  e, 
                  Token('BC', ']', 0, 99),
                 ])

        if self.debug: print('expr_eval:', Gcode.reconstruct(e))

        stack = list()
        brain = list()
        s = ''


        if i == None:
            i = 0

        t = e.toks[i]
        if type(t) == Token and len(e.toks) == 0:
            return 0
        if type(t) == Token and t.type != "BO":
            raise Exception(f'expression eval must start with a "["' + Gcode.where(t))
        if type(t) == Token and t.type == "BO":
            bo = 1
            i = 0
            # note we skip the first token. loop exits when bo back to 0

        lhs = -1
        while True:
           # get another token
           i += 1
           if i > len(e.toks)-1:
               raise Exception(f'Bad expression. Eval ran out of tokens')
           t = e.toks[i]

           if type(t) == FuncCall:
               # go get eval some args
               Gcode.show_stack(e, stack, brain)
               brain.append(t.name)

               print("func name:", t.name)
               for argi in range(len(t.args)):
                   print("func arg:", argi, t.args[argi])
                   if type(t.args[argi]) == Expr:
                       arg, __x = self._expr_eval(t.args[argi])
                       stack.append(arg)
                   elif type(t.args[argi]) == Token:
                       stack.append(t.args[argi].value)

               Gcode.show_stack(e, stack, brain)
               # then fall thru to operate on them
               pass

           elif t.type in self.arity and  '_fn' in t.type:
               # For _op arity is used for arg count
               raise Exception(f'parser error raw func toks should be wrapped in FuncCall')

           elif t.type == 'BO':
               bo += 1
               lhs = -1
               continue

           elif t.type == 'BC':
               bo -= 1
               #  All expression are encased in [ ] so exit when count
               #  is back to zero. This is way function args terminate
               #  if this is called recursively inside a stip
               if bo == 0:
                   if len(stack) > 1 or len(brain) > 0:
                      self.warn.append(f' Eval finished but left items on stack. Occured at: ' + Gcode.where(t))
                      Gcode.show_stack(e, stack, brain)
                   return stack[0], i
               continue

           elif t.type == 'NUMBER' or t.type == 'NUMBER2':
               stack.append(t.value)
               lhs = len(stack)-1

           elif t.type == 'binary_op':
               # When to convert a binary_op to a unary_op
               #     A number with a leading + or -
               if lhs < 0:
                  if t.value == '-':
                      t = Token('unary_op', 'CHS', t.lineno, t.column)
                  elif t.value == '+':
                      t = Token('unary_op', 'IDENTITY', t.lineno, t.column)
                  else:
                      raise Exception(f'do not know how to convert binary_op to unary_op: ' + Gcode.where(t))
 
               brain.append(t)
               continue

           else:
               raise Exception(f'unknown tok type in expression at line:{t.lineno} column:{t.column} got {t.type}')

           #print("try to operate ...")
           #print("   stacklen=", len(stack), "i=", i, "ntoks=", len(e.toks), "bo=",bo)
           while True:
               #Gcode.show_stack(e, stack, brain)
               #print("at the end?", "stacklen=", len(stack), "i=", i, "ntoks=", len(e.toks), "bo=",bo)
               if len(brain) == 0:
                   # doctor cannot be trusted
                   break

               # This depends on airity[type] is an int
               if len(stack) - self.arity[brain[-1].type] < 0:
                   # not enough numbers on the stack
                   break

               # Precedence is not defined for all values
               if e.toks[i+1].value in self.precedence: 
                   pright = self.precedence[e.toks[i+1].value]
               else:
                   pright = -1

               if brain[-1].value in self.precedence:
                   pbrain = self.precedence[brain[-1].value]
               else:
                   pbrain = -1

               if pbrain >= pright:
                   value = Gcode.stack_op(stack, brain.pop().value)
                   lhs = len(stack)-1
                   # stack and brain changed so go back and try for another
                   continue

               break # no more operations possible

           continue # with new token

    #staticmethod
    def show_stack(e, stack, brain, i=None):
        print('    expr_eval:', Gcode.reconstruct(e))
        print("    stack:",  stack)
        for b in brain: print("    brain:", b)

    #staticmethod
    def reconstruct(thing):
        s = ''
        if type(thing) == Expr:
            for t in thing.toks:
                if type(t) == Token:
                    s = s + ' ' + str(t.value)
                else:
                    s = s + Gcode.reconstruct(t)
            return s
        elif type(thing) == FuncCall:
            f = thing.name.value
            for a in thing.args:
                f = f + Gcode.reconstruct(a)
            return f
        elif type(thing) == Assign:
            return Gcode.reconstruct(thing.name) + '=' + Gcode.reconstruct(thing.expr)
        elif type(thing) == Token:
            return str(thing.value)
        elif type(thing) == int:
            return str(thing)
        elif type(thing) == float:
            return str(thing)
        else:
            raise Exception(f' do not know about thing: {type(thing)}')

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
        elif op == 'IDENTITY': pass
        elif op == 'CHS':   stack.append( -1.0 * stack.pop() )
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
        self.markstart = None
        self.markstop = None
        self.warn = []


    def program_finish(self):
        if self.markstart != None and self.markstop == None:
            self.warn.append(f"Found a start marker at line {self.markstart} but no stop marker")

        self.print_warn()


    def list_tokens(self, tokgen):
        print("-------- list_tokens() ----------")
        tok = next(tokgen, self.default_tok)
        if tok == self.default_tok:
            return
        while True:
            tok = next(tokgen, self.default_tok)
            print("    ", tokenstr(tok))
            if tok == self.default_tok:
                break


    def process_line(self, tokgen):
        tok = next(tokgen, self.default_tok)
        if tok == self.default_tok:
            return
        if tok.type == 'MARKEND':
            return
        codes, tok = self.collect_line(tokgen, tok)
        self.motion_apply(codes)


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
            print(f'process_tokens: line {lineno:4d}: {codes}') 

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
            #print("top of loop. tok=", tok)
            if tok.lineno != lineno:
                break

            # each branch below should deliver a fresh token here
            # print(f'  {tok.lineno:4d}  {tok.type:20s}  {tok.value}')
            if tok.type == 'word':
                word = tok.value

                tok = next(tokgen, self.default_tok)
                if tok.type == "NUMBER":
                   value = tok.value
                   tok = next(tokgen, self.default_tok)
                elif tok.value == "-":
                   tok = next(tokgen, self.default_tok)
                   value = -tok.value
                   tok = next(tokgen, self.default_tok)
                elif tok.value == "A":
                   value, tok = self.collect_function_call(tokgen, tok, prefix='A')
                   print('\n\n\nfunc call:', value, '\n\n\n')
                elif tok.type == "BO":
                   value, tok = self.collect_expression(tokgen, tok)
                elif tok.type == 'POINTER':
                   value, tok = self.collect_ptrderef(tokgen, tok)
                elif "_fn" in tok.type:
                   value, tok = self.collect_function_call(tokgen, tok)
                   print('\n\n\nfunc call:', value, '\n\n\n')
                else:
                   raise Exception(f'cannot figure out this value: ' + Gcode.where(tok))

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
        print(f'{"":20s} assignment start:' + tokenstr(tok))

        if tok.type != 'POINTER':
            raise Exception(f'line: {lineno}: Parser Error. Got here by mstake. token type:{tok.type}, value:{tok.value}')

        varname, tok = self.collect_ptrderef(tokgen, tok)

#        # variable access is always indirect.  #address, or ##adress
#        name = list()
#        name.append(tok)
#        while True:
#            tok = next(tokgen, self.default_tok)   # should be assigment op
#            if tok.type == 'ASSIGN':
#                break
#
#            if tok.lineno != lineno:
#                raise Exception(f'line: {lineno-1}: found EOL while looking for "=". Got {name}')
#
#            name.append(tok)

        if tok.type != 'ASSIGN':
            raise Exception(f'Expected "=" :' + Gcode.where(tok))

        tok = next(tokgen, self.default_tok)   # should be expression
        if tok.type == 'BO':
            value, tok = self.collect_expression(tokgen, tok)
        else:
            value = tok
            tok = next(tokgen, self.default_tok) # must feed the caller

        return Assign(varname, value), tok


    def collect_function_call(self, tokgen, tok, prefix=''):
        lineno = tok.lineno

        if prefix !='':
            # Fix up the case where ATAN gets split into A TAN
            # Same for ACOS and ASIN
            # This is context dependent. Caller decides.
            tok = next(tokgen, self.default_tok)
            tok = Token(tok.type, prefix + tok.value , tok.lineno, tok.column)

        func = tok
        func_type = tok.type
        func_name = tok.value

        args = list()

        tok = next(tokgen, self.default_tok)

        if func_type in self.arity:
            # An arity spec by value will override the arity for the type
            # For G-code this handles the funky ATAN
            if func_name in self.arity:
                print("arity for", func_name, self.arity[func_name])
                for argt in self.arity[func_name]:
                    if argt == Expr:
                        arg, tok = self.collect_expression(tokgen, tok)
                        args.append(arg)
                    elif argt == Token:
                        args.append(tok)
                        tok = next(tokgen, self.default_tok)
                    else:
                        raise Exception(f'unknown type airty' + Gcode.where(t) + self.arity[func_name])

            # The default arity is a sequence of Expr
            else:
                 for argc in range(self.arity[func_type]):
                     arg, tok = self.collect_expression(tokgen, tok)
                     args.append(arg)
        else:
            raise Exception(f'parser error, arity is undefined for function call: {func_name}:' + Gcode.where(tok))

        if tok.lineno > lineno:
            raise Exception(f'parser error, function args ran passed end of line: {func_name}:' + Gcode.where(tok))

        return FuncCall(func, args), tok

    def collect_ptrderef(self, tokgen, tok):
        lineno = tok.lineno
        print(f'{"":20s} pointer   start:' + tokenstr(tok))
        tok = next(tokgen, self.default_tok)

        if tok.type == 'BO':
            value, tok = self.collect_expression(tokgen, tok)
        else:
            print(f'{"":20s} pointer  address:' + tokenstr(tok))
            value = tok
            tok = next(tokgen, self.default_tok)

        return PtrDeRef(value), tok

    def collect_expression(self, tokgen, tok):
        # expressions are always bound by [ ]
        lineno = tok.lineno
        print(f'{"":20s} epression start:' + tokenstr(tok))

        if tok.type != 'BO':
            raise Exception(f'parser error, not an expression:' + Gcode.where(tok))

#        if tok.type == 'NUMBER':
#            val = tok.value
#            tok = next(tokgen, self.default_tok)
#            #print(f'{"":20s} epression   {tok.lineno:4d}  {tok.type:20s}  {tok.value}')
#            if tok.type == 'word' or tok.lineno != lineno:
#                # all good, no expr to parse
#                #print(f'{"":20s} epression  retruning a number: {expr}')
#                return val, tok

        # collect expr toks in a list. Include the opening [
        e = list()
        e.append(tok)
        bo = 1
        tok = next(tokgen, self.default_tok)
        # Note that in this loop:
        #    continue must insure a fresh token is supplied
        #    break must leave with the current token
        while True:
            if tok.type == 'BO':
                bo += 1

            elif tok.type == 'BC':
                bo -= 1
                if bo == 0:
                   e.append(tok)
                   break
                # stiil in the expr 

            elif "_fn" in tok.type:
                fncall, tok = self.collect_function_call(tokgen, tok)
                e.append(fncall)
                continue

            elif tok.type == 'word':
                break

            elif 'COM' in tok.type:
                tok = next(tokgen, self.default_tok)
                continue

            elif tok.lineno != lineno:
                break

            # still here?
            print(f'{"":20s} epression      :' + tokenstr(tok))
            e.append(tok)
            tok = next(tokgen, self.default_tok)

        #  last tok should have been a ]
        print(f'{"":20s} epression  last:' + tokenstr(tok))
        if tok.type == 'BC':
            # fresh one for caller
            tok = next(tokgen, self.default_tok)
            print(f'{"":20s} epression  next:' + tokenstr(tok))
        else:
            raise Exception(f'expression is missing closing "]":' + Gcode.where(tok))

        # type it for later
        return Expr(e), tok

    @staticmethod
    def where(tok):
        return f'line:{tok.lineno} column:{tok.column} "{tok.value}"'
 

    def parse_expr(self, gcode: bytes):
        " For testing expression parsing"
        # prepend 'X' to make this valid gcode
        gcode = b'x' + gcode
        gcode = gcode.decode(encoding='utf-8').upper()

        print(f'\nparse_expr(): input line: {gcode}') 
        self.warn = []

        tokgen = Gcode.tokenize(gcode)
        self.list_tokens(tokgen)

        tokgen = Gcode.tokenize(gcode)
        tok = next(tokgen, self.default_tok)
        codes, tok = self.collect_line(tokgen, tok)
        print(f'\n\nline  {codes}') 
 
        self.expr_show(e = codes['X'])

        self.warn = []
        val = self.expr_eval(e = codes['X'])
        print(f'parse_expr(): returning: {val}') 
        self.print_warn()

        return float(val)

    def parse_inc(self, gcode: bytes):
        gcode = gcode.decode(encoding='utf-8').upper()
        tokgen = Gcode.tokenize(gcode)
        self.process_tokens(tokgen)

    def parse_gcode(self, gcode: bytes):
        self.program_init()
        tokgen = Gcode.tokenize(gcode.decode(encoding='utf-8').upper())
        self.list_tokens(tokgen)
        self.program_finish()

        tokgen = Gcode.tokenize(gcode.decode(encoding='utf-8').upper())
        self.program_init()
        self.process_tokens(tokgen)
        self.program_finish()


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


class gcode_test:
    def __init__(self, debug=False) -> None:
        self.gc = Gcode(debug=False)

    def test_stack_op(self):
        self.gc.stacktest()

    def test_expr(self):
        ep = lambda e: self.gc.parse_expr(e)
        close = lambda e, want, lim=1e-6: abs(1 - float(self.gc.parse_expr(e)) / want) < lim
        error = lambda e, want: abs(1 - float(self.gc.parse_expr(e)) / want)

        assert( ep(b'1') == 1)
        assert( ep(b'[1+2]') == 3)

        assert( ep(b'[1]') == 1)
        assert( ep(b'[[1]]') == 1)
        assert( ep(b'[.1]') == 0.1)
        assert( ep(b'[+1]') == 1)
        assert( ep(b'[-1]') == -1)
        assert( ep(b'[3-2]') == 1)
        assert( ep(b'[.11]') == 0.11)
        assert( ep(b'[-.123]') == -0.123)
        assert( ep(b'[1+2]') == 3)
        assert( ep(b'[1 + 2 * 3 - 4 / 5]') == 6.2)
        assert( ep(b'[15 MOD 4.0]') == 3)
        assert( ep(b'[0 XOR 0]') == 0)
        assert( ep(b'[0 XOR 1]') == 1)
        assert( ep(b'[1 XOR 1]') == 0)
 
        assert( close( b'[2**3]', 8.0 ))
        assert( close( b'[2**3]', 8.0 ))
        assert( close( b'[1.2+sin[30]]', 1.7 ))
        assert( close( b'[sin[30]]', 0.5 ))
        assert( close( b'sqrt[3]', 1.732051 ))
        assert( close( b' atan[1.7321]/[1.0]', 60.0, 1e-3 ))

    def test_assign(self):
        pg = lambda e: self.gc.parse_gcode(e)
        #pg(b'n0040 g1 z-0.5 (start H)')
        #pg(b'n0190 g3 x13.5 y0 i-2.5')
        #pg(b'n0410 x [2 ** 3.0] #1=2.0 (x should be 8.0)')

    def test_inc(self):
       self.gc.program_init()
       self.gc.parse_inc(b'f[123*2]')
       self.gc.parse_inc(b'x654')

       assert(self.gc.f == 246)
       assert(self.gc.x == 654)

if __name__ == '__main__':


    gct = gcode_test()

    gct.test_stack_op()
    gct.test_expr()
    gct.test_assign()
    gct.test_inc()
    #exit(0)

    import gcode_samples

    samples = [
               gcode_samples.gc1,
               gcode_samples.gc2,
               gcode_samples.gc_hello_world,
#               gcode_samples.gc_expression_test
              ]

    gcode = Gcode()
    for gc in samples:
        print(gc.decode(encoding='utf-8').upper())

        gcode.parse_gcode(gc)
