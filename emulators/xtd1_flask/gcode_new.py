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

class BExpr(NamedTuple):
    toks: list[Token|FuncCall]

class Assign(NamedTuple):
    name: Strip
    expr: BExpr|Strip

class GcodeParser():
    ''' A G-Code Parser based on RS274NGC

        reference:
            The NIST RS274NGC Interpreter - Version 3
            Kramer, Proctro, Messina August 17, 2000 

        machine - A machine object to deal with parser output
                  If none is given then a mock will be used.
    '''
    def __init__(self, machine = None, debug=False) -> None:

        self.arity: dict
        self.precedence: dict
        self.warn: list[str]
        self.marks: list[str]

        self.debug = debug
        s = self
        self.default_tok = Token('END', 'end', -1, -1)

        token_info = GcodeParser.token_info()
        #print("token_info:", token_info)

        s.arity = dict()
        s.arity['unary_op'] = 1
        s.arity['binary_op'] = 2
        s.arity['unary_fn'] = 1
        s.arity['binary_fn'] = 2
        s.arity['ternary_fn'] = 3
        s.arity['ATAN'] = [BExpr, Token , BExpr]
        # example: ATAN [ Y expr ] / [ X expr ]  we accept expr op expr as args

        s.precedence = dict()
        s.precedence['#'] = 4
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

        # tok types and values that trigger an epression parse
        eo = []
        for k in token_info['funcs']:
            eo.append(k)
        eo.append('NUMBER')
        eo.append('NUMBER2')
        eo.append('[')
        eo.append('#')
        eo.append('-')
        eo.append('+')
        self.expr_openers = eo
        # tok types and values that terminate an epression parse
        # "]" is not in this list because it only terminates B-expressions.
        # B-expression parse will happen if the opening tok is "["
        et = []
        et.append('=')
        et.append('word')
        et.append('end')
        et.append('COMMENT')
        et.append('COMMENTP')
        self.expr_terminators = et

        self.warn = []
        self.marks = list()
        self.lineno = 0
        self.logger = None

        self.machine = None
        self.mem = None
        self.command_apply = None

        self.attach_machine(machine)


    def attach_machine(self, machine):
        """Set machine object that will host mem[] and recieve parsed codes

        machine - target object

        Consider extending this to a list of machines so a monitor could be
        tee'd in.
        """
        if machine == None:
            self.machine = None
            self.mem = dict()
            self.command_apply = self.mock_command_apply
            self.mem_init()
        else:
            self.machine = machine
            self.mem = self.machine.mem
            self.command_apply = self.machine.command_apply


    def mem_init(self):
        self.mem['S'] = 0
        self.mem['F'] = 0
        self.mem['X'] = 0
        self.mem['Y'] = 0
        self.mem['Z'] = 0

    def mock_command_apply(self, codes):
        # For testing a stand alone parser
        # Just go though all the codes and eval them
        if self.debug: print("mock command_apply:")

        for letter in codes:
            if letter == 'assigns': continue
            if letter in 'GM': continue
            #print(letter)
            if self.debug: print(codes[letter])
            self.mem[letter] = self.expr_eval(codes[letter])
            print(f'   {letter} = {self.mem[letter]}')

        self.S = self.mem['S']
        self.F = self.mem['F']
        self.X = self.mem['X']
        self.Y = self.mem['Y']
        self.Z = self.mem['Z']

        if 'assigns' in codes:
            for a in codes['assigns']:
                if self.debug: print(a.name)
                t = a.name.toks.pop(0)
                if t.value != '#':
                    raise Exception(f'Assignment. rhs does not have "#": ' + Gcode.where(t))
                rhs = self.expr_eval(a.name)
                lhs = self.expr_eval(a.expr)
                if self.debug: print("assign:", "rhs=", rhs, "lhs=", lhs)
                self.mem[int(rhs)] = lhs

        print("mem:")
        for a in self.mem:
            print("    ", a, self.mem[a])
        pass

    @staticmethod
    def token_info():
        "Common launguage definitions useful to the tokenizer and the parser"

        lettercodestr = 'ABCDFGHIJKLMPQRSTXYZ'
        lettercodes = []
        for kw in lettercodestr:
            lettercodes.append(kw)

        unary_op = ['#']
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
                'unary_op' : unary_op,
                'binary_op' : binary_op,
                'unary_fn' : unary_fn,
                'binary_fn' : binary_fn,
                'ternary_fn' : ternary_fn,
                'funcs' : funcs
               }


    @staticmethod
    def tokenize(code, line_count = None, col_count = None, logger = None):
        """G-Code tokenizer

           line_count - inflences the lineno field in Tokens
           col_count -  inflences the column field in Tokens

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

        token_info = GcodeParser.token_info()
 
        keywords = token_info['lettercodes']
        funcs = token_info['funcs']
        unary_op = token_info['unary_op']
        binary_op = token_info['binary_op']
        unary_fn = token_info['unary_fn']
        binary_fn = token_info['binary_fn']
        ternary_fn = token_info['ternary_fn']

        # Numbers with leading signs?  +3.4 -2.1
        # The tokenizer classifies thes as:  binary_op  NUMBER
        # These are handled in expr_eval() with a
        # binary_op to unary_op replacement when no a_val is detected
        #    as in,  a_val - b_val
        #       vs     ?   - b_val

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
            ('OP',       r'(#)|([*][*])|([+\-*/])'),  # Arithmetic operators
            ('NEWLINE',  r'\n'),           # Line endings
            ('SKIP',     r'[ \t]+'),       # Skip over spaces and tabs
            ('BO',       r'\['),           # expression
            ('BC',       r'\]'),           # expression
            ('RADIX',    r'\.'),           # decimal point get it own token
            ('MISMATCH', r'.'),            # Any other character
        ]
        tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in token_specification)
        if debug_tok: print("regex", tok_regex)

        line_num = 1
        line_start = 0

        if line_count != None:
            line_num = line_count + 1

        if col_count != None:
            line_start = col_count

        for mo in re.finditer(tok_regex, code):
            kind = mo.lastgroup
            value = mo.group()
            column = mo.start() - line_start

            if logger != None: logger(kind, value, line_num, column)
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

            elif kind == 'OP' and value in unary_op:
                kind = 'unary_op'

            elif kind == 'ID' and value in unary_fn:
                kind = 'unary_fn'
 
            elif kind == 'ID' and value in binary_fn:
                kind = 'binary_fn'
  
            elif kind == 'ID' and value in ternary_fn:
                kind = 'ternary_fn'

            elif kind == 'NEWLINE' or kind == 'MARK':
                line_start = mo.end()
                line_num += 1

                if kind == 'MARK':
                    yield Token(kind, value, line_num, column)

                continue

            elif kind == 'SKIP':
                continue

            elif kind == 'MISMATCH':
                raise RuntimeError(f'{value!r} unexpected on line {line_num}')

            if debug_tok: print(f'{"":10s} new token  line:{line_num:4d} col:{column:2d}  {kind:20s}  {value}')
            yield Token(kind, value, line_num, column)



    def expr_show(self, e:BExpr|FuncCall|Strip|Token|int|float = 0):
        print('\n\n--- expr_show ---')
        s = GcodeParser.reconstruct(e)
        print(s)
        print('--- expr_show end---')
        return


    def expr_eval(self, e:BExpr|FuncCall|Strip|Token|int|float = 0, i=None):
        result, i = self._expr_eval(e = e, i = i)
        return result
    
    def _expr_eval(self, e:BExpr|FuncCall|Strip|Token|int|float = 0, i=None):
        if self.debug: print('expr_eval:', GcodeParser.reconstruct(e))

        if type(e) == BExpr:
            pass
        #  a plain FuncCall must be wrapped in [ ]
        elif type(e) == FuncCall:
            e = BExpr(toks = [
                  Token('BO', '[', 0, 0),
                  e, 
                  Token('BC', ']', 0, 99),
                 ])
        elif type(e) == Strip:
            if self.debug: print("Strip")
            e.toks.insert(0, Token('BO', ']', 0, 0))
            e.toks.append(Token('BC', ']', 0, 99))
            if self.debug: print("Strip", e)
        elif type(e) == Token:
            return e.value, 0
        elif type(e) == int:
            return e, 0
        elif type(e) == float:
            return e, 0
        else:
            raise Exception(f'cannot evalute thing : ' + str(type(e)))

        stack: list
        brain: list
        stack = list()
        brain = list()
        s = ''
        if i == None:
            i = 0

        if len(e.toks) < i+1:
            raise Exception(f'parse error. tried to parse expression out of token rqange: ' + GcodeParser.where(e.toks[0]))

        t = e.toks[i]
        if type(t) != Token:
            raise Exception(f'expression is not a Token : ' + str(t))
        if t.type != "BO":
            raise Exception(f'expression eval must start with a "[": ' + GcodeParser.where(t))
        else:
            bo = 1
            # note we skip the first token. loop exits when bo back to 0

        if self.debug: print(f'{"":20s} expr_eval  start:' + tokenstr(t))

        a_val: str|int

        a_val = '?'
        while True:
           # get another token
           i += 1
           if i > len(e.toks)-1:
               raise Exception(f'Bad expression. Eval ran out of tokens')
           t = e.toks[i]

           if self.debug and type(t) == Token: print(f'{"":20s} expr_eval  tok {i}:' + tokenstr(t))

           if type(t) == FuncCall:
               # go get eval some args
               if self.debug: GcodeParser.show_stack(e, stack, brain)
               brain.append(t.name)

               if self.debug: print("func name:", t.name)
               for argi in range(len(t.args)):
                   if self.debug: print("func arg:", argi, t.args[argi])
                   arg, __x = self._expr_eval(t.args[argi])
                   stack.append(arg)
                   a_val = len(stack)-1

               if self.debug: GcodeParser.show_stack(e, stack, brain)
               # then fall thru to operate on them
               pass

           elif t.type in self.arity and  '_fn' in t.type:
               # For _op arity is used for arg count
               raise Exception(f'parser error raw func toks should be wrapped in FuncCall: ' + GcodeParser.where(t))

           elif t.type == 'BO':
               bo += 1
               a_val = '?'
               continue

           elif t.type == 'BC':
               bo -= 1
               #  All expression are encased in [ ] so exit when count
               #  is back to zero. This is way function args terminate
               #  if this is called recursively inside a stip
               if bo == 0:
                   if len(stack) > 1 or len(brain) > 0:
                      self.warn.append(f' Eval finished but left items on stack. Occured at: ' + GcodeParser.where(t))
                      if self.debug: GcodeParser.show_stack(e, stack, brain)
                   return stack[0], i
               continue

           elif t.type == 'NUMBER' or t.type == 'NUMBER2':
               stack.append(t.value)
               a_val = len(stack)-1

           elif t.type == 'unary_op':
               brain.append(t)
               continue

           elif t.type == 'binary_op':
               # When to convert a binary_op to a unary_op
               #     A number with a leading + or -
               #     [ -1 + 1 ]  = 0
               #     [ 1 --1 ]   = 2
               if a_val == '?':
                  if t.value == '-':
                      t = Token('unary_op', 'CHS', t.lineno, t.column)
                  elif t.value == '+':
                      t = Token('unary_op', 'IDENTITY', t.lineno, t.column)
                  else:
                      raise Exception(f'do not know how to convert binary_op to unary_op: ' + GcodeParser.where(t))
                  brain.append(t)
                  continue
               else:
                  brain.append(t)
                  a_val = '?'   # pushed a binary so previos a val is claimed
                  continue

           else:
               raise Exception(f'unknown tok type in expression {t.type}, {t.value} at :' + GcodeParser.where(t))

           #print("try to operate ...")
           #print("   stacklen=", len(stack), "i=", i, "ntoks=", len(e.toks), "bo=",bo)
           while True:
               #GcodeParser.show_stack(e, stack, brain)
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
                   value = self.stack_op(stack, brain.pop().value)
                   a_val = len(stack)-1
                   # stack and brain changed so go back and try for another
                   continue

               break # no more operations possible

           continue # with new token

    @staticmethod
    def show_stack(e, stack, brain, i=None):
        print('    expr_eval:', GcodeParser.reconstruct(e))
        print("    stack:",  stack)
        for b in brain: print("    brain:", b)

    @staticmethod
    def reconstruct(thing):
        s = ''
        if type(thing) == BExpr:
            for t in thing.toks:
                if type(t) == Token:
                    s = s + ' ' + str(t.value)
                else:
                    s = s + GcodeParser.reconstruct(t)
            return s
        elif type(thing) == FuncCall:
            f = thing.name.value
            for a in thing.args:
                f = f + GcodeParser.reconstruct(a)
            return f
        elif type(thing) == Strip:
            f = ''
            for a in thing.toks:
                f = f + GcodeParser.reconstruct(a)
            return f
        elif type(thing) == Assign:
            return GcodeParser.reconstruct(thing.name) + '=' + GcodeParser.reconstruct(thing.expr)
        elif type(thing) == Token:
            return str(thing.value)
        elif type(thing) == int:
            return str(thing)
        elif type(thing) == float:
            return str(thing)
        else:
            raise Exception(f' do not know about thing: {type(thing)}')

    def stack_op(self, stack, op):
        # atan2 is ternary in the gcode language
        # we get atan2( y, '/', x)
        if op == '+':      stack.append( stack.pop() + stack.pop() )
        elif op == '-':    stack.append( stack.pop(-2) - stack.pop() )
        elif op == '*':    stack.append( stack.pop() * stack.pop() )
        elif op == '/':    stack.append( stack.pop(-2) / stack.pop() )
        elif op == '**':   stack.append( math.pow(stack.pop(-2), stack.pop()) )
        elif op == 'MOD':  stack.append( int(stack.pop(-2)) % int(stack.pop()) )
        elif op == 'OR':
           a = stack.pop()  # make sure we get two pops
           b = stack.pop()
           stack.append( bool(a) or bool(b) )
        elif op == 'AND':
           a = stack.pop()  # make sure we get two pops
           b = stack.pop()
           stack.append( bool(a) and bool(b) )
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
           #print("atan" , y, x)
           stack.append( math.atan2(y,x) * 180 / math.pi )
           #print("atan" , y, x, '=', stack[-1])
           #stack.append( math.atan2(stack.pop(-3) / stack.pop()) * 180 / math.pi )
        elif op == 'FUP':  stack.append( math.ceil(stack.pop()) )
        elif op == 'FIX':  stack.append( math.floor(stack.pop()) )
        elif op == 'ABS':  stack.append( abs(stack.pop()) )
        elif op == 'EXP':  stack.append( math.exp(stack.pop()))
        elif op == 'LN':   stack.append( math.log(stack.pop()))
        elif op == 'SQRT':  stack.append( math.sqrt(stack.pop()) )
        elif op == 'ROUND': stack.append( round(stack.pop()) )
        elif op == 'IDENTITY': pass
        elif op == 'CHS':   stack.append( -1.0 * stack.pop() )
        elif op == '#':    stack.append( self.mem_get(stack.pop()) )
        else: raise Exception(f' do not know about operation: {op}')
        return stack[-1]


    def mem_get(self, addr):
        if addr in self.mem:
            return self.mem[addr]
        else:
            self.mem[addr] = 0
            return 0


    def stacktest(self):
        stack = list()

        stack.append(1)
        stack.append(3)
        stack.append(2)
        #print(stack)
        x = self.stack_op(stack, '*')
        x = self.stack_op(stack, '+')
        #print(stack)
        #print(x)
        assert(x == 7)

        stack.append(2)
        x = self.stack_op(stack, '/')
        #print(x)
        assert(x == 3.5)

        stack.append(3)
        stack.append(2)
        x = self.stack_op(stack, 'MOD')
        assert(x == 1)

        stack.append(-0.499)
        x = self.stack_op(stack, 'ROUND')
        assert(x == 0)

        stack.append(-0.501)
        x = self.stack_op(stack, 'ROUND')
        assert(x == -1)

        stack.append(2.44)
        x = self.stack_op(stack, 'ROUND')
        assert(x == 2)

        stack.append(9.975)
        x = self.stack_op(stack, 'ROUND')
        assert(x == 10)



    def list_tokens(self, tokgen):
        print("-------- list_tokens() ----------")
        self.lineno += 1
        tok = next(tokgen, self.default_tok)
        if tok == self.default_tok:
            return
        while True:
            tok = next(tokgen, self.default_tok)
            print("    ", tokenstr(tok))
            if tok == self.default_tok:
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
            if tok.type == 'END':
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
                   #print('\n\n\nfunc call:', value, '\n\n\n')
                elif tok.type == "BO":
                   value, tok = self.collect_bexpression(tokgen, tok)
                elif tok.value in self.expr_openers or tok.type in self.expr_openers:
                   value, tok = self.collect_expression(tokgen, tok)
                elif "_fn" in tok.type:
                   value, tok = self.collect_function_call(tokgen, tok)
                   #print('\n\n\nfunc call:', value, '\n\n\n')
                else:
                   raise Exception(f'cannot figure out this value: ' + GcodeParser.where(tok))

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

            elif tok.value in self.expr_openers or tok.type in self.expr_openers:
                lhs, tok = self.collect_expression(tokgen, tok)
                if tok.type == 'ASSIGN':
                    tok = next(tokgen, self.default_tok)
                    rhs, tok = self.collect_expression(tokgen, tok) 
                    if not 'assigns' in codes:
                        codes['assigns'] = list()
                    codes['assigns'].append(Assign(lhs, rhs))
                else:
                    self.warn.append(f'Floater expression: ' + GcodeParser.where(tok))
                continue

            elif 'COM' in tok.type:
                tok = next(tokgen, self.default_tok)
                continue

            elif tok.type == 'MARK':
                self.marks.append(tok)
                tok = next(tokgen, self.default_tok)
                continue

            elif tok.type == 'LINENO':
                tok = next(tokgen, self.default_tok)
                continue

            if self.debug: print("bottom of loop. tok=", tok)
            # blame it on the gcode
            raise Exception(f'line:{lineno} column:{tok.column}  invalid syntax {tok.type}, value:{tok.value}')
            # still here? we mssed up
            raise Exception(f'line: {lineno}: unhandled token type, {tok.type}, value:{tok.value}')

        return codes, tok

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
                if self.debug: print("arity for", func_name, self.arity[func_name])
                for argt in self.arity[func_name]:
                    if argt == BExpr:
                        arg, tok = self.collect_bexpression(tokgen, tok)
                        args.append(arg)
                    elif argt == Token:
                        args.append(tok)
                        tok = next(tokgen, self.default_tok)
                    else:
                        raise Exception(f'unknown type airty' + GcodeParser.where(t) + self.arity[func_name])

            # The default arity is a sequence of BExpr
            else:
                 for argc in range(self.arity[func_type]):
                     arg, tok = self.collect_bexpression(tokgen, tok)
                     args.append(arg)
        else:
            raise Exception(f'parser error, arity is undefined for function call: {func_name}:' + GcodeParser.where(tok))

        if tok.lineno > lineno:
            raise Exception(f'parser error, function args ran passed end of line: {func_name}:' + GcodeParser.where(tok))

        return FuncCall(func, args), tok


    def collect_expression(self, tokgen, tok):
        """Permissive expression collector
        Terminators defined by self.expr_terminators[]

        An illegal postfix op will also terminate an expression
        rather than flag an error.
        This allows parsing:

        """
        break_on_unary = False
        lineno = tok.lineno
        if self.debug: print(f'{"":20s} epression start:' + tokenstr(tok))
        if tok.type == 'BO':
            return self.collect_bexpression(tokgen, tok)
        e = list()
        while True:
            if tok.value in self.expr_terminators:
                break
            elif tok.type in self.expr_terminators:
                break
            elif tok.lineno != lineno:
                break
            elif 'COM' in tok.type:
                break
            elif tok.type == 'unary_op' and break_on_unary:
                break
            elif "_fn" in tok.type:
                fncall, tok = self.collect_function_call(tokgen, tok)
                e.append(fncall)
                break_on_unary = True
                continue

            if tok.type == 'binary_op' or tok.type == 'unary_op':
                break_on_unary = False
            else:
                break_on_unary = True

            if self.debug: print(f'{"":20s} epression      :' + tokenstr(tok))
            e.append(tok) # first token is the "["
            tok = next(tokgen, self.default_tok)

        if self.debug: print(f'{"":20s} epression  next:' + tokenstr(tok))
        return Strip(e), tok


    def collect_bexpression(self, tokgen, tok):
        """ B expressions are bound by [ ]
            tokgen - a generator that yeilds <Token>
            tok - current token, should be a "["
            returns a <BExpr>
        """
        lineno = tok.lineno
        if self.debug: print(f'{"":20s} bepression start:' + tokenstr(tok))
        if tok.type != 'BO':
            raise Exception(f'parser error, not an expression:' + GcodeParser.where(tok))

        e = list()
        e.append(tok) # first token is the "["
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

            # hack to handle inverse trig funcs
            elif tok.value == "A":
                fncall, tok = self.collect_function_call(tokgen, tok, prefix='A')
                e.append(fncall)
                continue

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
            if self.debug: print(f'{"":20s} bepression      :' + tokenstr(tok))
            e.append(tok)
            tok = next(tokgen, self.default_tok)

        #  last tok should have been a "]"
        if self.debug: print(f'{"":20s} bepression  last:' + tokenstr(tok))
        if tok.type == 'BC':
            # fresh one for caller
            tok = next(tokgen, self.default_tok)
            if self.debug: print(f'{"":20s} bepression  next:' + tokenstr(tok))
        else:
            raise Exception(f'expression is missing closing "]":' + GcodeParser.where(tok))

        return BExpr(e), tok


    @staticmethod
    def where(tok):
        return f'line:{tok.lineno} column:{tok.column} "{tok.value}"'


    def print_warn(self):
        for i in self.warn:
            print(f'WARN: {i}')


    def program_init(self, logger = None):
        self.logger = logger
        self.markstart = None
        self.markstop = None
        self.warn = []
        self.marks = list()
        self.lineno = 0


    def program_finish(self):
        if self.markstart != None and self.markstop == None:
            self.warn.append(f"Found a start marker at line {self.markstart} but no stop marker")

        self.print_warn()


    def process_line(self, tokgen):
        tok = next(tokgen, self.default_tok)
        if tok == self.default_tok:
            return
        if tok.type == 'MARKEND':
            return
        codes, tok = self.collect_line(tokgen, tok)
        self.command_apply(codes)


    def process_program(self, tokgen):
        #codes = dict()
        tok = next(tokgen, self.default_tok)
        if tok == self.default_tok:
            return
        if tok.type == 'MARKEND':
            return

        while True:
            lineno = tok.lineno
            codes, tok = self.collect_line(tokgen, tok)
            if self.debug: print(f'process_tokens: line {lineno:4d}: {codes}') 

            self.command_apply(codes)

            if tok.type == 'MARKEND':
               break
            if tok.type == 'END':
               break
 

    def parse_expr(self, gcode: bytes, logger = None):
        " For testing expression parsing"
        # prepend 'X' to make this valid gcode
        gcode = b'x' + gcode

        gcodes : str
        gcodes = gcode.decode(encoding='utf-8').upper()

        print(f'\nparse_expr(): input line: {gcodes}') 
        self.warn = []

        tokgen = GcodeParser.tokenize(gcodes, logger = logger)
        self.list_tokens(tokgen)

        tokgen = GcodeParser.tokenize(gcodes)
        tok = next(tokgen, self.default_tok)
        codes, tok = self.collect_line(tokgen, tok)
        print(f'\n\nline  {codes}') 
 
        self.expr_show(e = codes['X'])

        self.warn = []
        val = self.expr_eval(e = codes['X'])
        print(f'parse_expr(): returning: {val}') 
        self.print_warn()

        return float(val)


    def parse_inc(self, gcode: bytes, logger = None):
        if gcode == None: return
        if logger != None: logger = logger
        else: logger = self.logger

        gcodes : str
        gcodes = gcode.decode(encoding='utf-8').upper()
        tokgen = GcodeParser.tokenize(gcodes, line_count = self.lineno, logger = logger)
        self.lineno += 1
        self.process_line(tokgen)


    def parse_gcode(self, gcode: bytes):
        self.program_init()
        tokgen = GcodeParser.tokenize(gcode.decode(encoding='utf-8').upper())
        self.list_tokens(tokgen)
        self.program_finish()

        tokgen = GcodeParser.tokenize(gcode.decode(encoding='utf-8').upper())
        self.program_init()
        self.process_program(tokgen)
        self.program_finish()


class CANON_UNITS(Enum):
    MM = 1
    INCH = 2

class CANON_DISTANCE_MODE(Enum):
    ABSOLUTE = 1
    INCREMENTAL = 2

class CANON_AXIS(Enum):
    X = 1
    Y = 2
    Z = 3

class CANON_PLANE(Enum):
    XY = 1
    YZ = 2
    XZ = 3

class CANON_FEED_REFERENCE(Enum):
    WORKPIECE = 1
    XYZ = 2

class CANON_MOTION_MODE(Enum):
    EXACT_STOP = 1
    EXACT_PATH = 2
    CONTINUOUS = 3

class CANON_DIRECTION(Enum):
    STOPPED = 1
    CLOCKWISE = 2
    COUNTERCLOCKWISE = 3

class CANON_SPEED_FEED_MODE(Enum):
    SYNCHED = 1
    INDEPENDENT = 2

class CANON_COMP_SIDE(Enum):
    RIGHT = 1
    LEFT = 2

class Axis(NamedTuple):
    x: float
    y: float
    z: float
    a: float
    b: float
    c: float


class GcodeMachine:
    def __init__(self, parser = None, debug = False) -> None:


        self.G_group: dict
        self.M_group: dict
        self.groupname: dict
        self.group: dict
        self.group_of: dict
        self.state: dict
        self.status: dict
        self.config: dict
        self.mem: dict


        self.debug = debug
        self.state = dict()
        self.status = dict()
        self.config = dict()
        self.mem = dict()

        if parser == None:
            parser = GcodeParser(machine = self)

        self.parser = parser

        s = self
        s.G_group = dict()
        s.M_group = dict()
        s.groupname = dict()

        # https://docs.python.org/3/glossary.html#term-list-comprehension
        #s.Groupname = list( 'undefined' for i in range(17) )

       #                      name                inital code value

        s.groupname['G'] = [ ['non_modal',                   0  ],  # 0
                             ['motion',                      0  ],  # 1
                             ['plane_selection',             17  ],  # 2
                             ['distance_mode',               90  ],  # 3
                             ['undefined',                   0  ],  # 4
                             ['feed_rate_mode',              93  ],  # 5
                             ['units',                       21  ],  # 6
                             ['cutter_radius_compensation',  40  ],  # 7
                             ['tool_length_offset',          43  ],  # 8
                             ['undefined',                   0  ],  # 9
                             ['canned_cycle_return_mode',    98  ],  # 10
                             ['scaling',                     50  ],  # 11
                             ['coordinate_system_selection', 54 ],  # 12
                             ['undefined',                   0  ],  # 13
                             ['undefined',                   0  ],  # 14
                             ['path_control_mode',           61 ],  # 15
                            ]

        s.groupname['M'] = [ ['stopping',                    0  ], 
                             ['tool_change',                 0  ], 
                             ['spindle_turning',             0  ], 
                             ['coolant',                     0  ], 
                             ['speed_feed_override',         0  ], 
                             ['user_defined_m',              0  ], 
                        ]

        self.active =  dict()
        self.feed =  dict()
        self.spindle =  dict()

        s.group = dict()
        for letter in s.groupname:
            s.group[letter] = dict()
            for name,default in s.groupname[letter]:
                s.group[letter][name] = dict()
                self.active[name] = default

        #self.feed[ self.active['motion'] ] = 0
        #self.spindle[ self.active['motion'] ] = 0


        # ection 3.4, table 4
        # The modal groups for G codes are:
        #  38.2 probe, 80-89 canned cycles
        s.group['G']['motion'] = (0, 1, 2, 3, 38.2, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89)
        s.group['G']['plane_selection'] = (17, 18, 19)
        s.group['G']['distance_mode'] = (90, 91)
        s.group['G']['feed_rate_mode'] = (93, 94)
        s.group['G']['units'] = (20, 21)
        s.group['G']['cutter_radius_compensation'] = (40, 41, 42)
        s.group['G']['tool_length_offset'] = (43, 49)
        s.group['G']['canned_cycle_return_mode'] = (98, 99)
        s.group['G']['scaling'] = (50, 51)
        s.group['G']['coordinate_system_selection'] = (54, 55, 56, 57, 58, 59, 59.1, 59.2, 59.3)
        s.group['G']['path_control_mode'] = (61, 61.1, 64)
        # In addition to the above modal groups, there is a group for non-modal G codes:
        s.group['G']['non_modal'] = (4, 10, 28, 30, 53, 92, 92.1, 92.2, 92.3)

        # names here should not be groupnames.
        # one for each setting that is not in modal group
        self.active['dwell'] = 0   # G4
        self.active['origin'] = 0   # G10
                                    # G28 return to home
                                    # G30 return to secondary home
                                    # G53 move absolute
        self.active['user_config'] = 101

        # 10, 28, 30, and 92 axis words suspend motion group axis settings

        # The modal groups for M codes are:
        s.group['M']['stopping'] = (0, 1, 2, 30, 60)
        s.group['M']['tool_change'] = [6]
        s.group['M']['spindle_turning'] = (3, 4, 5)
        s.group['M']['coolant'] = (7, 8, 9)
        s.group['M']['speed_feed_override'] = (48, 49)
        s.group['M']['user_defined_m'] = (17, 18, 97, 106)
        s.group['M']['user_config'] = (101, 205, 207)

        for code in s.group['G']['motion']:
            self.feed[code] = 0
            self.spindle[code] = 0

        # make a lookup table for G and M code groups
        s.group_of = dict()
        for letter in s.group:
            s.group_of[letter] = dict()
            print(letter)
            for name in s.group[letter]:
                print(letter, name)
                for code in s.group[letter][name]:
                    print(letter, name, code)
                    s.group_of[letter][code] = name


        # parameter access functions used in call tables
        f = lambda codes : self.command_param('F', codes)
        S = lambda codes : self.command_param('S', codes)
        t = lambda codes : self.command_param('T', codes)
        p = lambda codes : self.command_param('P', codes)
        r = lambda codes : self.command_param('R', codes)
        i = lambda codes : self.command_param('I', codes)
        j = lambda codes : self.command_param('J', codes)
        x = lambda codes : self.command_param('X', codes)
        y = lambda codes : self.command_param('Y', codes)

        all_codes = lambda codes : codes
        cmd_axis = lambda codes : self.command_axis(codes)
        gopt = lambda code : re.sub(r'^\d+\.', '', code)  # digits after '.'


        # Section 3.8, table 8
        # list of group name or func name and arg list
        # in this list order
        #     group name  -  handle codes in that group if there are any
        #                    could be a G group or an M group
        #                    dewell is the only special case. 
        #     func, args  -  run the func with evaluated args
        self.exec_order: list = [
                 [ 'user_config', []],
                 [ 'feed_rate_mode',    []],
                 [ self.set_feed_rate,          [all_codes]],
                 [ self.set_spindle_speed, [S]],
                 [ self.select_tool,       [t]],
                 [ 'tool_change',       []],
                 [ 'spindle_turning',   []],
                 [ 'coolant',           []],
                 [ 'speed_feed_override', []],
                 [ 'user_defined_m', []],
                 [ self.do_dwell_command,        [all_codes]], # special case
                 [ 'plane_selection',    []],
                 [ 'units',              []],
                 [ 'cutter_radius_compensation',  []],
                 [ 'tool_length_offset',   []],
                 [ 'coordinate_system_selection', []],
                 [ 'path_control_mode', []],
                 [ 'distance_mode', []],
                 [ 'canned_cycle_return_mode', []],
                 [ 'non_modal', []],                    # expect dewll
                 [ self.__do_motion, [all_codes]],
                 [ 'stopping', []]
                ]

        call_builder = list()
        call_builder = [
            [ 'G',  0, self.rapid,          [cmd_axis, f, S]],
            [ 'G',  1, self.linear,         [cmd_axis, f, S]],
            [ 'G',  2, 'arc_cw',         [cmd_axis, r, i, j]],
            [ 'G',  3, 'arc_ccw',        [cmd_axis, r, i, j]],

            [ 'G', 38, 'probe',          [cmd_axis, gopt, ]],

            [ 'G', 80, 'cancel_modal_motion', []],
            [ 'G', 81, 'drill_cycle',       [cmd_axis, r, f, S]],
            [ 'G', 82, 'drill_cycle_dwell', [cmd_axis, r, f, S, p]],


            #[ 'G',  4, self.do_dwell,          [p]],
            [ 'G',  4, self.no_op,          []],          # dwell handled earlier in sequence. why?

            [ 'G', 17, self.set_plane,  ['XY']],
            [ 'G', 18, self.set_plane,  ['XZ']],
            [ 'G', 19, self.set_plane,  ['YZ']],
            [ 'G', 20, self.use_length_units,  ['inch']],
            [ 'G', 21, self.use_length_units,  [ 'mm']],
            [ 'G', 40, self.not_implemented,   ['G40']],

            [ 'G', 53, self.move_absolute,   [cmd_axis]],
            [ 'G', 54, 'coord_system',   [1]],
            [ 'G', 55, 'coord_system',   [2]],
            [ 'G', 56, 'coord_system',   [3]],
            [ 'G', 57, 'coord_system',   [4]],
            [ 'G', 58, 'coord_system',   [5]],
            [ 'G', 59, 'coord_system',   [6]],
            [ 'G', 59.1, 'coord_system',   [7]],
            [ 'G', 59.2, 'coord_system',   [8]],
            [ 'G', 59.3, 'coord_system',   [9]],
            [ 'G', 90, self.set_distance_mode,       [90, 'absolute']],
            [ 'G', 91, self.set_distance_mode,       [91, 'incremental']],
            [ 'G', 92, self.set_origin_offsets,   [cmd_axis]],
            [ 'G', 93, self.set_feed_rate_mode,   ['units_per_min']],
            [ 'G', 94, self.set_feed_rate_mode,   ['inverse_time']],
            [ 'M', 0, self.not_implemented,   ['M0']],
            [ 'M', 17, self.xtd1_enable,  []],
            [ 'M', 18, self.xtd1_disable,  []],
            [ 'M', 97, self.xtd1_cross_hair_sticky, [S]],
            [ 'M', 101, self.xtd1_M101,  []],
            [ 'M', 106, self.xtd1_cross_hair,  [S]],
            [ 'M', 205, self.xtd1_extents,  [x,y]],
            [ 'M', 207, self.xtd1_M207,  [S]],
           ]


        self.ok = dict()
        self.ok['distance_mode'] =  ['absolute', 'incremental']
        self.ok['feed_rate_mode'] = ['units_per_min', 'inverse_time']
        self.ok['plane'] = ['XY', 'XZ', 'YZ']
        self.ok['length_units'] = ['inch', 'mm']

        ct = self.build_call_table(call_builder)
        for letter in ct:
            for code in ct[letter]:
                func, args = ct[letter][code]
                print(letter, code, func, args)

        print("ct=",ct)

        self.call_table = ct

        self.init_machine()

    def init_machine(self):
        self.init_mem()
        self.init_state()

        self.set_distance_mode(90, 'absolute')
        self.set_plane('XY')
        self.set_feed_rate_mode('units_per_min')
        self.use_length_units('mm')


    def init_mem(self):
        self.mem = dict()
        self.mem['S'] = 0
        self.mem['F'] = 0
        self.mem['X'] = 0
        self.mem['Y'] = 0
        self.mem['Z'] = 0
        self.mem['A'] = 0
        self.mem['B'] = 0
        self.mem['C'] = 0

    def init_state(self):
        self.state['F'] = 0
        self.state['S'] = 0
        self.state['X'] = 0
        self.state['Y'] = 0
        self.state['Z'] = 0
        self.state['A'] = 0
        self.state['B'] = 0
        self.state['C'] = 0
        self.update_shortcuts()

    def update_shortcuts(self):
        self.F = self.state['F']
        self.S = self.state['S']
        self.X = self.state['X']
        self.Y = self.state['Y']
        self.Z = self.state['Z']
        self.A = self.state['A']
        self.B = self.state['B']
        self.C = self.state['C']
        print(self.state)


    def build_call_table(self, b):
        ct = dict()
        for c in b:
           letter = c.pop(0)
           if not letter in ct: ct[letter] = dict()
           code = c.pop(0)
           func = c.pop(0)
           args = c.pop(0)
           ct[letter][code] = [func, args]
        return ct


    def program_init(self, logger = None):
        self.parser.program_init (logger = logger)

    def parse_inc(self, gcode: bytes, logger = None, expect=None):
        self.expect = expect
        self.parser.parse_inc (gcode, logger = logger)

    def command_apply(self, codes):
        try:
            self.__command_apply(codes)

        except Exception as e:
            if str(e) == self.expect:
                print(str(e), " ... but it was expected")
                self.expect = None
                pass
            else:
                raise(e)

        if self.expect != None:
            raise Exception("Expected an error but it did not occur: " + self.expect)

    def __command_apply(self, codes):
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
        # Others, only one allowed. Already enfoced by the parser

        ggroups = list()
        mgroups = list()

        g = dict()
        m = dict()

        # validate 1 G code per group
        if 'G' in codes:
            for code in codes['G']:
                gname = self.group_of['G'][code]
                if gname in ggroups:
                    raise Exception("more than one G code from same group")
                else:
                    ggroups.append(gname)
                    g[gname] = code

        # validate 1 M code per group, maximum 4 codes
        if 'M' in codes:
            for code in codes['M']:
                mname = self.group_of['M'][code]
                if mname in mgroups:
                    raise Exception("more than one M code from same group")
                else:
                    mgroups.append(mname)
                    m[mname] = code
            if len(mgroups) > 4:
                raise Exception("more than four M codes")

        # evaluate expressions 
        for letter in codes:
            if letter == 'assigns': continue
            if letter in 'GM': continue
            #print(letter)
            if self.debug: print(codes[letter])
            self.mem[letter] = self.parser.expr_eval(codes[letter])
            print(f'   {letter} = {self.mem[letter]}')


        # some funcs called by exec_order list will use thie
        #if 'motion' in g:
        #    self.active['motion'] = g['motion']

        for name in self.group["G"]:
            if name in g and name != 'non_modal':
                self.active[name] = g[name]

        for name in self.group["M"]:
            if name in m and name != 'non_modal':
                self.active[name] = m[name]

        for a in self.active:
            print("active", a, self.active[a])


        # go through the todo list 
        for thing, args in self.exec_order:
            print("thing =", thing)
            if type(thing) == str and thing in self.group["G"]:
                print("   group G", thing, self.active[thing])
                if thing in g:
                    func, args = self.call_table['G'][g[thing]]
                    #func, args = self.call_table['G'][self.active[thing]]
                    self.__do_exec_func(codes, func, args)
            elif type(thing) == str and thing in self.group["M"]:
                print("   group M", thing, self.active[thing])
                if thing in m:
                    func, args = self.call_table['M'][m[thing]]
                    #func, args = self.call_table['M'][self.active[thing]]
                    self.__do_exec_func(codes, func, args)
            elif str(type(thing)) == "<class 'method'>":
                print("   func")
                self.__do_exec_func(codes, thing, args)
            else:
                raise Exception(f'exec order: unknown thing {type(thing)}, {thing}')


        # variable assignments 
        if 'assigns' in codes:
            for a in codes['assigns']:
                if self.debug: print(a.name)
                t = a.name.toks.pop(0)
                if t.value != '#':
                    raise Exception(f'Assignment. rhs does not have "#": ' + Gcode.where(t))
                rhs = self.parser.expr_eval(a.name)
                lhs = self.parser.expr_eval(a.expr)
                if self.debug: print("assign:", "rhs=", rhs, "lhs=", lhs)
                self.mem[int(rhs)] = lhs

        print("mem:")
        for a in self.mem:
            print("    ", a, self.mem[a])
        pass


    def __do_exec_func(self, codes, func, args):
        ae = list()
        for arg in args:
            print("arg =", arg)
            if type(arg) == str:
                argv = arg
            elif type(arg) == int:
                argv = arg
            else:
                argv = arg(codes)
            print("argv =", argv)
            ae.append(argv)
        func(*ae)


    def __do_motion(self, codes):
        # all parameters are evaluated and in mem[]
        # feeds and speed have been updated
        # now do the thing ... linear or arc 

        # set spindle and feed per the current motion group
        self.state['S'] = self.spindle[self.active['motion']]
        self.state['F'] = self.feed[self.active['motion']]

        c = self.call_table['G'][self.active['motion']]
        print("__do_motion", c)
        func = c[0]
        args = c[1]

        self.__do_exec_func(codes, func, args)


    def command_axis(self, codes):
        return Axis(
                    self.command_param('X', codes),
                    self.command_param('Y', codes),
                    self.command_param('Z', codes),
                    self.command_param('A', codes),
                    self.command_param('B', codes),
                    self.command_param('C', codes)
                   )

    def current_pos(self) -> Axis:
        return Axis(
                    self.state['X'],
                    self.state['Y'],
                    self.state['Z'],
                    self.state['A'],
                    self.state['B'],
                    self.state['C']
                   )

    def mock_delay(self, delay):
        print(f'{"":30s}-------mock delay {delay} sec')
        pass

    def mock_move_to(self, axis, feed):
        if self.active['distance_mode'] == 90:  # abs
            self.state['X'] = axis.x
            self.state['Y'] = axis.y
            self.state['Z'] = axis.z
            self.state['A'] = axis.a
            self.state['B'] = axis.b
            self.state['C'] = axis.c
        elif self.active['distance_mode'] == 91:  # inc
            print("move to incremental")
            self.state['X'] += axis.x
            self.state['Y'] += axis.y
            self.state['Z'] += axis.z
            self.state['A'] += axis.a
            self.state['B'] += axis.b
            self.state['C'] += axis.c
        else:
            raise Exception(f'error distance mode?: self.active["distance_mode"]')
        self.update_shortcuts()

    def generic_set(self, p, mode):
        if not mode in self.ok[p]:
            raise Exception(f'set_{p}: got {mode}: expected: {self.ok[p]}')
        # self.active[groupname] = code
        #self.active[p] = mode


    def no_op(self):
        pass

    # These are from rs274/NGC page 44 table 9
    # Representation 
    def init_canon(self):
        pass
    def end_canon(self):
        pass

    def set_plane(self, plane:CANON_PLANE):
        self.generic_set('plane', plane)
        pass

    def command_param(self, letter, codes):
        "return a value from the current command or from the current machine state"
        val = 0
        if letter in codes:
            val = self.mem[letter]
        elif letter in self.state:
            val = self.state[letter]
        else:
            return 0
        return val


    def not_implemented(self, msg:str):
        print("not implemented:", msg)
 
 
    #def set_origin_offsets(self, x:float, y:float, z:float, a:float, b:float, c:float):
    def set_origin_offsets(self, codes):
        """Says to the machine: Your current position is x, y, z, a, b, c

        XTool D1 usage is to relate the LED cross hair position
        to the desired mahine (0,0).

            G92 X17 Y1 (machine 0,0 is where the LED crosshair is)

        At the end of the program, you may want to park the LED back at 0,0:

            G0 X17 Y1
        """

        self.active['offset'] = self.command_axis(codes)

        pass

    def use_length_units(self, units:CANON_UNITS):
        self.generic_set('length_units', units)

    def set_distance_mode(self, code, mode:CANON_DISTANCE_MODE):
        self.generic_set('distance_mode', mode)
        self.active['distance_mode'] = code

    # Free Space Motion
    def set_traverse_rate(self, rate:float):
        # desired rapid rate, machine may limit at a lower rate
        pass

    def straight_traverse(self, axis: Axis):
        # no cutting expected
        pass

    # Machining Attributes
    def set_feed_rate_mode(self, mode):
        self.generic_set('feed_rate_mode', mode)
        pass

    def set_feed_rate(self, codes):
        if 'F' in codes:
            self.feed[ self.active['motion'] ] = self.mem['F']
        # set rate to use for active mode
        pass

    def set_feed_reference(self, reference:CANON_FEED_REFERENCE):
        # WORKPIECE or XYZ
        # ref mode is WORKPIECE
        #   units per minute along the path
        # ref mode is XYZ
        #   deg per minute around one axis
        pass
    def set_motion_control_mode(self, mode:CANON_MOTION_MODE):
        # EXACT_STOP, EXACT_PATH, CONTINUOUS
        pass
    def start_speed_feed_synch(self):
        # for thread tapping
        pass
    def stop_speed_feed_synch(self):
        # for not thread tapping
        pass


    # Machining Functions
    def rapid(self, axis:Axis, f=None, s=None):
        # some redundency here 
        if f != self.feed[0]:
            raise Exception(f'command parser error. feedrate mismatch')

        self.mock_move_to(axis, self.feed[0])
        print("---rapid---", axis, f, s)


    def linear(self, axis:Axis, f=None, s=None):
        # some redundency here 
        if f != self.feed[1]:
            raise Exception(f'command parser error. feedrate mismatch')

        self.mock_move_to(axis, self.feed[1])
        print("---linear---", axis, f, s)
        pass

    def move_absolute(self, axis:Axis, f=None, s=None):
        """G53 move absolute using feed rate
        from G0 or G1, whichever is active.
        if active motion mode is not 0 or 1 then error
        """
        if self.active['motion'] == 0:
            pass
        elif self.active['motion'] == 1:
            pass
        else:
            raise Exception(f'move_absolute: active motion mode is not G0 or G1: have mode = G{self.active["motion"]}')

        self.mock_move_to(axis, self.feed[ self.active['motion'] ])
 

    def arc_cw(self, x=None, y=None, z=None, a=None, b=None, c=None, r=None, i=None, j=None):
        pass
    def arc_ccw(self, x=None, y=None, z=None, a=None, b=None, c=None, r=None, i=None, j=None):
        pass
    def arc(self, dir=None, x=None, y=None, z=None, a=None, b=None, c=None, r=None, i=None, j=None):
        # dir 'cw" or 'ccw'
        # At least one axis word in the current working plane must be supplied
        # x,y,z are the end point
        # radius format:
        #    r if supplied is the radius
        # center format:
        #    end point can be same as start point (circle)
        #    i,j are offsets to the center, at least one required
        pass


    def arc_feed(self, first_end:float, second_end:float,
                       first_axis:float, second_axis:float,
                       rotation:int, axis_end_point:float,
                       a:float, b:float, c:float):
        # helical arc
        # first and second refer to the plane we are in. 
        # For XY, X and Y are first and second. axis_end_point is Z at the end of the arc
        # rotation poisitive is CCW
        # arc starts at current pos and ends at (first_end, second_end)
        pass

    def do_dwell_command(self, codes):
        # if G4 in codes then dwell self.mem[P] seconds
        # delay
        print("do_dwell_command", codes)
        if 'G' in codes and 4 in codes['G']:
            self.active['dwell'] = self.mem['P']   # G4
            print("do_dwell_command")
            self.mock_delay(self.command_param('P', codes))

    def do_dwell(self, p):
        # called for a G4,  p is from the command line, zero is not present
        # delay
        if p > 0:
            self.active['dwell'] = p

        print("do_dwell")
        self.mock_delay(p)


    def ellipse_feed(self,
                       major:float, minor:float,
                       first_end:float, second_end:float,
                       first_axis:float, second_axis:float,
                       rotation:int, axis_end_point:float,
                       a:float, b:float, c:float):
        # helical elliptic arc
        # first and second refer to the plane we are in. 
        # For XY, X and Y are first and second. axis_end_point is Z at the end of the arc
        # rotation poisitive is CCW
        # arc starts at current pos and ends at (first_end, second_end)
        pass
    def stop(self):
        # come briefly to a stop after finishing the previous move
        pass
    def straight_feed(self, x:float, y:float, z:float, a:float, b:float, c:float):
        pass
    # Probe Functions
    def straight_probe(self, x:float, y:float, z:float, a:float, b:float, c:float):
        pass
    # Spindle Functions
    def orient_spindle(self, orientation:float, direction:CANON_DIRECTION):
        pass
    def set_spindle_speed(self, r:float):
        # set speed but do not turn spindle on
        # if already on, leave it on, change the speed, 
        pass
    def spindle_retract(self):
        # at feed rate
        pass
    def spindle_retract_traverse(self):
        # at rapid rate
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
    def use_tool_length_offset(self, offset:float):
        pass

    # Miscellaneous Functions
    def clamp_axis(self, axis:CANON_AXIS):
        # error is move is attemted on a clamed axis
        pass
    def unclamp_axis(self, axis:CANON_AXIS):
        # error is move is attemted on a clamed axis
        pass
    def comment(self, s:str):
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
    def message(self, s:str):
        # console msg
        pass
    def mist_off(self):
        pass
    def mist_on(self):
        pass
    def pallet_shuttle(self):
        pass
    # Program Functions
    def optional_program_stop(self):
        # an optional pause with option to continue
        pass
    def program_stop(self):
        # an forced pause with option to continue
        pass
    def program_end(self):
        if self.markstart != None and self.markstop == None:
            self.warn.append(f"Found a start marker at line {self.markstart} but no stop marker")
        # get ready for a new program or shutdown

    def set_cutter_radius_compensation(self, radius:float):
        pass
    def start_cutter_radius_compensation(self, side:CANON_COMP_SIDE):
        pass
    def stop_cutter_radius_compensation(self):
        pass

    # xtool specific
    #   when running a file via the button, /progress returns:
    #      progress  indicates percent, 0 to 100
    #      working   becomse a time counter, looks like ms. It keeps counting after the file is done
    #      lines     indicates current gcode line

    #   to reset the timer: upload a new cut file, press the button.
    #
    def xtd1_enable(self):
        # M17 steppers enable, led green
        self.status["working"] = 1
        self.state["led_cross"] = 0
        # xtd1 will timeout after a few sec of no actvity and disable
        pass

    def xtd1_disable(self):
        # M18
        self.status["working"] = 0
        self.state["led_cross"] = 0
        pass

    def xtd1_cross_hair(self, s):
        # M106S1  cross on, reset by M17 and M18
        if s >= 1:
           self.state["led_cross"] = 1
        else:
           self.state["led_cross"] = 0

    def xtd1_cross_hair_sticky(self, s):
        # M97S0  turns cross on when idle. persistent across power cycles
        # M97S1  turns off
        if s == 1:
           self.state["led_cross"] = 1

    def xtd1_extents(self, x, y):
        # M205 X432 Y403
        self.config["extentx"] = x
        self.config["extenty"] = y

    def xtd1_M207(self, s):
        # ? M207 S1
        pass

    def xtd1_M101(self):
        # ?
        pass




class gcode_test:
    def __init__(self, debug=False) -> None:
        self.gc = GcodeParser(debug=False)
        self.debug = debug

        self.lineno = 0
        self.tokstr = ''

    def test_stack_op(self):
        self.gc.stacktest()

    def test_expr_parse(self):
        ep = lambda e: self.gc.parse_expr(e)
        close = lambda e, want, lim=1e-6: abs(1 - float(self.gc.parse_expr(e)) / want) < lim
        absclose = lambda e, want, lim=1e-6: abs(float(want) - float(self.gc.parse_expr(e))) < float(lim)
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
        assert( absclose( b' sin[[2.0+1.14159]*180/3.14159]', 0.0, 1e-3 ))

    def test_expr(self):
        close =    lambda val, want, lim=1e-6: abs(1.0 - float(val) / float(want)) < lim
        absclose = lambda val, want, lim=1e-6: abs(float(want) - float(val)) < float(lim)
        exact = lambda val, want: val == want
        x = '?'
        w = '?'
        g = [
              [ x, w, 0,    b'n0020 x [1 + 2] (x should be 3)'],
              [ x, w, 0,    b'n0030 x [1 - 2] (x should be -1)'],
              [ x, w, 0,    b'n0040 x [1 --3] (x should be 4)'],
              [ x, w, 1e-4, b'n0050 x [2/5] (x should be 0.40)'],
              [ x, w, 0,    b'n0060 x [3.0 * 5] (x should be 15)'],
              [ x, w, 0,    b'n0070 x [0 OR 0] (x should be 0)'],
              [ x, w, 0,    b'n0080 x [0 OR 1] (x should be 1)'],
              [ x, w, 0,    b'n0090 x [2 or 2] (x should be 1)'],
              [ x, w, 0,    b'n0100 x [0 AND 0] (x should be 0)'],
              [ x, w, 0,    b'n0110 x [0 AND 1] (x should be 0)'],
              [ x, w, 0,    b'n0120 x [2 and 2] (x should be 1)'],
              [ x, w, 0,    b'n0130 x [0 XOR 0] (x should be 0)'],
              [ x, w, 0,    b'n0140 x [0 XOR 1] (x should be 1)'],
              [ x, w, 0,    b'n0150 x [2 xor 2] (x should be 0)'],
              [ x, w, 0,    b'n0160 x [15 MOD 4.0] (x should be 3)'],
              [ x, w, 1e-4, b'n0170 x [1 + 2 * 3 - 4 / 5] (x should be 6.2)'],
              [ x, w, 1e-4, b'n0180 x sin[30] (x should be 0.5)'],
              [ x, w, 1e-4, b'n0190 x cos[0.0] (x should be 1.0)'],
              [ x, w, 1e-4, b'n0200 x tan[60.0] (x should be 1.7321)'],
              [ x, w, 1e-4, b'n0210 x sqrt[3] (x should be 1.7321)'],
              [ x, w, 1e-4, b'n0220 x atan[1.7321]/[1.0] (x should be 60.0)'],
              [ x, w, 1e-4, b'n0230 x asin[1.0] (x should be 90.0)'],
              [ x, w, 1e-4, b'n0240 x acos[0.707107] (x should be 45.0000)'],
              [ x, w, 1e-4, b'n0250 x abs[20.0] (x should be 20)'],
              [ x, w, 1e-4, b'n0260 x abs[-1.23] (x should be 1.23)'],
              [ x, w, 0,    b'n0270 x round[-0.499] (x should be 0)'],
              [ x, w, 1e-4, b'n0280 x round[-0.5001] (x should be -1.0)'],
              [ x, w, 0,    b'n0290 x round[2.444] (x should be 2)'],
              [ x, w, 0,    b'n0300 x round[9.975] (x should be 10)'],
              [ x, w, 1e-4, b'n0310 x fix[-0.499] (x should be -1.0)'],
              [ x, w, 1e-4, b'n0320 x fix[-0.5001] (x should be -1.0)'],
              [ x, w, 1e-4, b'n0330 x fix[2.444] (x should be 2)'],
              [ x, w, 1e-4, b'n0340 x fix[9.975] (x should be 9)'],
              [ x, w, 1e-4, b'n0350 x fup[-0.499] (x should be 0.0)'],
              [ x, w, 1e-4, b'n0360 x fup[-0.5001] (x should be 0.0)'],
              [ x, w, 1e-3, b'n0370 x fup[2.444] (x should be 3)'],
              [ x, w, 1e-4, b'n0380 x fup[9.975] (x should be 10)'],
              [ x, w, 1e-4, b'n0390 x exp[2.3026] (x should be 10)'],
              [ x, w, 1e-4, b'n0400 x ln[10.0] (x should be 2.3026)'],
              [ x, w, 1e-4, b'n0410 x [2 ** 3.0] #1=2.0 (x should be 8.0)'],
              ['2', 0.375, 1e-4, b'n0420 ##1 = 0.375 (#1 is 2, so parameter 2 is set to 0.375)'],
              [ x, w, 1e-4, b'n0430 x #2 (x should be 0.375) #3=7.0'],
              [ x, w, 1e-4, b'n0440 #3=5.0 x #3 (parameters set in parallel, so x should be 7, not 5)'],
              [ x, w, 1e-4, b'n0450 x #3 #3=1.1 (parameters set in parallel, so x should be 5, not 1.1)'],
              [ x, w, 1e-4, b'n0460 x [2 + asin[1/2.1+-0.345] / [atan[fix[4.4] * 2.1 * sqrt[16.8]] /[-18]]**2]'],
              [ x, w, 1e-4, b'n0470 x sqrt[3**2 + 4**2] (x should be 5.0)'],
            ]

        self.gc.program_init(logger = self.toklog)

        for var, want, lim, code in g:
            try:
                self.gc.parse_inc(code)

                if [var,want] == ['?', '?']:
                    # mini parser to pull  [var] should be [value]
                    # out of comments
                    mo = re.search(r'([(])([^)]*)([)])', code.decode(encoding='utf-8'))
                    if mo:
                        comment = mo.group(2)
                        #print('comment=', comment)
                    else:
                        continue

                    regex = r'(?P<ID>[a-zA-Z])|(?P<NUMBER>-?\d+(\.\d*)?)|(?P<ASSERT> +should be +)'
                    tokgen = re.finditer(regex, comment)
                    asrt = False
                    for mo in tokgen:
                        kind = mo.lastgroup
                        value = mo.group()
                        #print(f' kind = {kind}   value = {value}')
                        if asrt:
                            want = value
                            break
                        if kind == 'ID':
                            var = value
                        if kind == 'ASSERT':
                            asrt=True

                #print("var,want", var, want)
                if var  == '?': continue
                if want == '?': continue
                # mem keys for variables are int
                if re.match(r'\d+', var): var = int(var)
                else: var = var.upper()

                if want == 0 and lim ==0:
                    assert( self.gc.mem[var] == want )
                elif abs(float(want)) < 1e-4 and float(lim) > 0:
                    assert( absclose( self.gc.mem[var], want, lim ) )
                elif lim == 0:
                    assert( int(self.gc.mem[var]) == int(want) )
                else:
                    assert( close( self.gc.mem[var], want, lim ) )

            except Exception as e:
                print("\ngot to here:", "line:", self.lineno, "toks:", self.tokstr + "\n")
                raise(e)


    def test_assign(self):
        #pg = lambda e: self.gc.parse_gcode(e)
        #pg(b'n0040 g1 z-0.5 (start H)')
        #pg(b'n0190 g3 x13.5 y0 i-2.5')
        #pg(b'n0410 x [2 ** 3.0] #1=2.0 (x should be 8.0)')

        try:
            self.gc.program_init(logger = self.toklog)
            p = self.gc.parse_inc

            p( b'n0410 x [2 ** 3.0] #1=2.0 (x should be 8.0)' )
            assert(self.gc.X == 8.0)
            assert(self.gc.mem[1] == 2.0)

            p( b'n0420 ##1 = 0.375 (#1 is 2, so parameter 2 is set to 0.375)' )
            assert(self.gc.mem[2] == 0.375)

            p( b'n0430 x #2 (x should be 0.375) #3=7.0' )
            assert(self.gc.X == 0.375)

            p( b'n0440 #3=5.0 x #3 (parameters set in parallel, so x should be 7, not 5)' )
            assert(self.gc.X == 7.0)

            p( b'n0450 x #3 #3=1.1 (parameters set in parallel, so x should be 5, not 1.1)' )
            assert(self.gc.X == 5.0)

            p( b'n0460 x [2 + asin[1/2.1+-0.345] / [atan[fix[4.4] * 2.1 * sqrt[16.8]] /[-18]]**2]' )
            p( b'n0470 x sqrt[3**2 + 4**2] (x should be 5.0)' )
            assert(self.gc.X == 5.0)

        except Exception as e:
            print("\ngot to here:", "line:", self.lineno, "toks:", self.tokstr + "\n")
            raise(e)


    def test_inc(self):
        self.gc.program_init(logger = self.toklog)
        self.gc.parse_inc(b'f[123*2]')
        self.gc.parse_inc(b'x654')
        self.gc.parse_inc(b'#1 = 3.14')
        self.gc.parse_inc(b'#2 = #1*2')
        assert(self.gc.F == 246)
        assert(self.gc.X == 654)
        self.gc.parse_inc(b'x654')


    def test_machine(self):
        close =    lambda val, want, lim=1e-6: abs(1.0 - float(val) / float(want)) < lim
        absclose = lambda val, want, lim=1e-6: abs(float(want) - float(val)) < float(lim)
        m = GcodeMachine(debug=True)
        m.program_init(logger = self.toklog)
        m.parse_inc(b'f[123*2]')
        assert(m.F == 246)

        m.parse_inc(b'G1 F600')
        m.parse_inc(b'G0 F3000')

        assert(m.feed[0] == 3000)
        assert(m.feed[1] == 600)

        m.parse_inc(b'G1 x10 f650')
        assert(m.feed[1] == 650)
        assert(m.feed[0] == 3000)
        assert(m.X == 10)
        assert(m.Y == 0)
        m.parse_inc(b'G92 x17 y1')
        assert(m.X == 17)
        assert(m.Y == 1)

        m.parse_inc(b'G1 x12.3 y3.14')
        m.parse_inc(b'G0 x0.1 y0.2')
        m.parse_inc(b'G0 x0.1 y0.2 G1', expect="more than one G code from same group")
        m.parse_inc(b'M0 M1',           expect="more than one M code from same group")
        m.parse_inc(b'M0 M6 M3 M7 M48', expect="more than four M codes")
        assert(m.X == 0.1)
        assert(m.Y == 0.2)

        m.parse_inc(b'x0y0')
        assert(m.X == 0)
        assert(m.Y == 0)

        m.parse_inc(b'g91')
        m.parse_inc(b'G4 P0.100')
        assert(m.active['dwell'] == 0.100)

        m.parse_inc(b'G91 G0 X0.1 Y0.2')
        m.parse_inc(b'X0.15 Y0.23')
        assert(absclose(m.X, 0.25))
        assert(absclose(m.Y, 0.43))

        m.parse_inc(b'G90 G0 X0 Y0')
        assert(absclose(m.X, 0.0))
        assert(absclose(m.Y, 0.0))

        m.parse_inc(b'M17S1')
        m.parse_inc(b'M106S1')

    def toklog(self, kind:str, value:str, lineno:int, col:int):
        if not self.debug: return
        print(f'log:  {lineno:4d} {col:2d} {kind:10s} {str(value):10s}')
        if lineno != self.lineno:
           self.lineno = lineno
           self.tokstr = value
        else:
           self.tokstr += value

if __name__ == '__main__':

    gct = gcode_test()

    gct.test_stack_op()
    gct.test_expr_parse()
    gct.test_expr()
    gct.test_inc()
    gct.test_assign()

    gct.test_machine()

    exit(0)

    import gcode_samples

    samples = [
               gcode_samples.gc1,
               gcode_samples.gc2,
               gcode_samples.gc_hello_world,
               gcode_samples.gc_expression_test
              ]

    gcode = GcodeParser()
    for gc in samples:
        print(gc.decode(encoding='utf-8').upper())

        gcode.parse_gcode(gc)


