from textwrap import dedent
from io import UnsupportedOperation
import math
import re
from textwrap import dedent

import path
from typing import NamedTuple
import re


gc1 = dedent(f'''
        %
        % sample gcode
        M17 S1  (enable steppers)
        G21     (mm units)
        M106 S1
        M205 X426 Y403
        M101
        G92 X17 (is this legal?) Y1 (two comments)
        G90
        G1 F3000
        G0 F3000
        G1 S0
        G0 X0 Y0
        G1X75.03 Y0
        G1X75.03Y53.92
        G1X0 Y53.92
        G1 X0 Y0
        G0 X17 Y1
        M18
        %
        ''').strip().encode('utf-8')

gc2 = dedent(f'''
        M17 S1
        M205 X426 Y403
        M101
        G90
        G92 X0 Y0
        G0 F3000
        G1 F600
        G1 S50
        G0 X51.20 Y29.09
        G1 X50.20 Y29.09 S60
        G1 X48.22 Y29.09
        G1 X45.24 Y29.09
        G1 X44.24 Y31.08
        G0 X0.000 Y0.000
        M18
        ''').strip().encode('utf-8')

# https://en.wikipedia.org/wiki/G-code
# from https://www.nist.gov/publications/nist-rs274ngc-interpreter-version-3?pub_id=823374
gc_hello_world = dedent(f'''
        (this program mills 'Hello world' between X=0 and X=81 millimeters)
        n0010 g21 g0 x0 y0 z50 (top of part should be on XY plane)
        n0020 t1 m6 m3 f20 s4000 (use an engraver or small ball-nose endmill)
        n0030 g0 x0 y0 z2
        n0040 g1 z-0.5 (start H)
        n0050 y10
        n0060 g0 z2
        n0070 y5
        n0080 g1 z-0.5
        n0090 x 7
        n0100 g0 z2
        n0110 y0
        n0120 g1 z-0.5
        n0130 y10
        n0140 g0 z2
        n0150 x11 y2.5
        n0160 g1 z-0.5 (start e)
        n0170 x16
        n0190 g3 x13.5 y0 i-2.5
        n0200 g1 x16
        n0210 g0 z2
        n0220 x20 y0
        n0230 g1 z-0.5 (start l)
        n0240 y9
        n0250 g0 z2
        n0260 x26
        n0270 g1 z-0.5 (start l)
        n0280 y0
        n0290 g0 z2
        n0300 x32.5
        n0310 g1 z-0.5 (start o)
        n0320 g2 x32.5 j2.5
        n0330 g0 z2
        n0340 x45 y5
        n0350 g1 z-0.5 (start w)
        n0360 x47 y0
        n0370 x48.5 y3
        n0380 x50 y0
        n0390 x52 y5
        n0400 g0 z2
        n0410 x57.5 y0
        n0420 g1 z-0.5 (start o)
        n0430 g2 x57.5 j2.5
        n0440 g0 z2
        n0450 x64
        n0460 g1 z-0.5 (start r)
        n0470 y5
        n0480 y4
        n0490 g2 x69 r4
        n0500 g0 z2
        n0510 x73 y0
        n0520 g1 z-0.5 (start l)
        n0530 y9
        n0540 g0 z2
        n0550 x81
        n0560 g1 z-0.5 (start d)
        n0570 y0
        n0580 x79.5
        n0590 g2 j2.5 y5
        n0600 g1 x81
        n0610 g0 z50
        n0620 m2
        ''').strip().encode('utf-8')

gc_expression_test = dedent(f'''
        n0010 g21 g1 x3 f20 (expression test)
        n0020 x [1 + 2] (x should be 3)
        n0030 x [1 - 2] (x should be -1)
        n0040 x [1 --3] (x should be 4)
        n0050 x [2/5] (x should be 0.40)
        n0060 x [3.0 * 5] (x should be 15)
        n0070 x [0 OR 0] (x should be 0)
        n0080 x [0 OR 1] (x should be 1)
        n0090 x [2 or 2] (x should be 1)
        n0100 x [0 AND 0] (x should be 0)
        n0110 x [0 AND 1] (x should be 0)
        n0120 x [2 and 2] (x should be 1)
        n0130 x [0 XOR 0] (x should be 0)
        n0140 x [0 XOR 1] (x should be 1)
        n0150 x [2 xor 2] (x should be 0)
        n0160 x [15 MOD 4.0] (x should be 3)
        n0170 x [1 + 2 * 3 - 4 / 5] (x should be 6.2)
        n0180 x sin[30] (x should be 0.5)
        n0190 x cos[0.0] (x should be 1.0)
        n0200 x tan[60.0] (x should be 1.7321)
        n0210 x sqrt[3] (x should be 1.7321)
        n0220 x atan[1.7321]/[1.0] (x should be 60.0)
        n0230 x asin[1.0] (x should be 90.0)
        n0240 x acos[0.707107] (x should be 45.0000)
        n0250 x abs[20.0] (x should be 20)
        n0260 x abs[-1.23] (x should be 1.23)
        n0270 x round[-0.499] (x should be 0)
        n0280 x round[-0.5001] (x should be -1.0)
        n0290 x round[2.444] (x should be 2)
        n0300 x round[9.975] (x should be 10)
        n0310 x fix[-0.499] (x should be -1.0)
        n0320 x fix[-0.5001] (x should be -1.0)
        n0330 x fix[2.444] (x should be 2)
        n0340 x fix[9.975] (x should be 9)
        n0350 x fup[-0.499] (x should be 0.0)
        n0360 x fup[-0.5001] (x should be 0.0)
        n0370 x fup[2.444] (x should be 3)
        n0380 x fup[9.975] (x should be 10)
        n0390 x exp[2.3026] (x should be 10)
        n0400 x ln[10.0] (x should be 2.3026)
        n0410 x [2 ** 3.0] #1=2.0 (x should be 8.0)
        n0420 ##1 = 0.375 (#1 is 2, so parameter 2 is set to 0.375)
        n0430 x #2 (x should be 0.375) #3=7.0
        n0440 #3=5.0 x #3 (parameters set in parallel, so x should be 7, not 5)
        n0450 x #3 #3=1.1 (parameters set in parallel, so x should be 5, not 1.1)
        n0460 x [2 + asin[1/2.1+-0.345] / [atan[fix[4.4] * 2.1 * sqrt[16.8]] /[-18]]**2]
        n0470 x sqrt[3**2 + 4**2] (x should be 5.0)
        n0480 m2
        ''').strip().encode('utf-8')

