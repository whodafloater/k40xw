#!/usr/bin/env python3
# 2025 whodafloater 
# MIT license

import gcode

import time
import math


class Animator:
    def __init__(self, bound=[0, 0, 400, 400], debug=False, *args, **kwargs):

        self.debug = debug
        self.bound = bound

        self.vmax = 50   # mm/sec
        self.amax = 500  # mm/sec^2
        self.vstop = 0.1 # mm/sec speed considered stopped
        self.ka = 10

        self.resolution = 0.1   # mm
        self.ipmm = int(1/self.resolution)  # ints per mm
        self.ivmax = self.vmax * self.ipmm
        self.iamax = self.amax * self.ipmm
        self.ivstop = self.vstop * self.ipmm

        # for educational purpose, a fancy pants way to scale a box.
        #    map returns an iterator
        #    list() iterates the map
        self.ibound = list(map(lambda val: val*self.ipmm, self.bound))
        #print(self.bound, self.ibound, type(self.ibound), type(self.ibound[0]))

        # current request
        self.destx = 0
        self.desty = 0
        self.feed = 0

        # current controller state
        self.headx = self.ibound[0]
        self.heady = self.ibound[1]
        self.vx = 0.0
        self.vy = 0.0
        self.v = 0.0
        self.a = 0.0
        self.power = 0
        self.led = False

        # current physical state 
        self.head_err = [0, 0]
        self.head_actual = [self.headx, self.heady] 

        self.time = time.time()
        self.timestep = 0.01

        self.movedone = True
        self.iter = 0

    def load_gcode():
        pass

    def reset(self):
        return self.headx, self.heady

    def program_move(self, x, y, feed, power, led):
        #                  mm mm mm/sec pct bool
        self.destx = int(x*self.ipmm)
        self.desty = int(y*self.ipmm)
        self.feed = feed
        self.movedone = False

        self.power = power
        self.led = led

        self.ifeed = self.feed * self.ipmm
        self.time = time.time()

    def compute_frame(self, time):
        if self.movedone:
            # nothing to do, jump to the present
            self.time = time
            self.power = 0
        else:
            # animate the move up to the request time
            t = self.time
            while t < time:
               t += self.timestep
               self._do_step()
            self.time = t

        return self.head_actual[0]/self.ipmm, self.head_actual[1]/self.ipmm, self.power, self.led

    def _do_step(self):
        x, y  = self.headx, self.heady
        vx, vy  = self.vx, self.vy
        tstep = self.timestep
        self.iter += 1

        destx, desty = self.destx, self.desty
        v = math.sqrt(vx*vx + vy*vy)

        if int(x) == destx and int(y) == desty and v < self.ivstop:
           self.movedone = True

        # how far to go.
        # at max accel,
        #    dist = 1/2 * a * t^2
        #    t = v / a
        # 
        #    dist = 1/2 * v^2 / a
        dx = (destx-x)
        dy = (desty-y)
        dtg = math.sqrt(dx*dx+dy*dy)
        dts = 0.5 * v * v / self.iamax

        if self.debug:
            print(f'    {self.iter:4d} x = {x:6.2f} y = {y:6.2f}  vx = {vx:5.2f} vy = {vy:5.2f} v = {v:5.2f} dtg = {dtg:0.1f}   dts = {dts:0.1f} dx = {dx:0.1f} dy = {dy:0.1f}')

        # control accel to stop on time
        # or to maintain desired feed
        ax = 0.0
        ay = 0.0
        a = 0.0

        if True:
            if dtg > 1.2*dts:
                dvx = dx/dtg * self.ifeed
                dvy = dy/dtg * self.ifeed
                ax = (dvx - vx) / tstep
                ay = (dvy - vy) / tstep
                if self.debug: print("  cruise  ", dvx, dvy, self.ifeed, ax, ay)
                ax = max(min(ax, self.iamax), -self.iamax)
                ay = max(min(ay, self.iamax), -self.iamax)

            else:
                # pick accel to stop at dtg
                if dtg / tstep > v:
                    a = 0.5 * v * v / dtg
                    #a = max(min(a, self.iamax), -self.iamax)
                    ax = -a * dx/dtg
                    ay = -a * dy/dtg
                    if self.debug: print("  target  ", self.ifeed, ax, ay)
                else: 
                    ax = 0
                    ay = 0
                    vx = dx / tstep
                    vy = dy / tstep
                    if self.debug: print("  finish  ", self.ifeed, vx, ay)

        vx = vx + ax*tstep
        vy = vy + ay*tstep

        vx = max(min(vx, self.ivmax), -self.ivmax)
        vy = max(min(vy, self.ivmax), -self.ivmax)

        x += (vx * tstep)
        y += (vy * tstep)

        xerr, yerr = self.head_err
        xa, ya = self.head_actual
        xa = x + xerr
        ya = y + yerr

        # belt tooth jump or stepper cog is like a instant bump in x,y
        if xa < self.ibound[0]:
           xerr += 20
        if xa > self.ibound[2]:
           xerr -= 20
        if ya < self.ibound[1]:
           yerr += 20
        if ya > self.ibound[3]:
           yerr -= 20

        xa = x + xerr
        ya = y + yerr

        self.head_err = [xerr, yerr]
        self.head_actual = [xa, ya]
        self.a = a
        self.v = v
        self.vx = vx
        self.vy = vy
        self.headx = x
        self.heady = y

        if self.debug: print(f'i = {self.iter:4d} x = {x:6.2f} y = {y:6.2f}  vx = {vx:5.2f} vy = {vy:5.2f} v = {v:5.2f} dtg = {dtg:0.1f}   dts = {dts:0.1f} dx = {dx:0.1f} dy = {dy:0.1f} ax = {ax:0.1f} ay = {ay:0.1f}')


if __name__ == '__main__':

    anim = Animator()
    anim.program_move(10, 0, 50, 5, 0)

    t0 = time.time()
    x, y = anim.compute_frame(t0+0.5)

    anim.program_move(20, 10, 50, 5, 0)
    t0 = time.time()
    x, y = anim.compute_frame(t0+0.5)

    anim.program_move(0, 0, 50, 5, 0)
    t0 = time.time()
    x, y = anim.compute_frame(t0+1.5)

    ti = time.time()
    timeout = 10.3
    anim.program_move(30, 20, 20, 5, 0)
    while anim.movedone == False and (ti-t0)<timeout:
       ti +=0.100
       x, y = anim.compute_frame(ti)

    ti = time.time()
    timeout = 10.3
    anim.program_move(-10, -10, 20, 5, 0)
    while anim.movedone == False and (ti-t0)<timeout:
       ti +=0.100
       x, y = anim.compute_frame(ti)

