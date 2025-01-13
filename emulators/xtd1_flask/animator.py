#!/usr/bin/env python3
# 2025 whodafloater 
# MIT license

import time
import math

import gcode
import path


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

        self.reset()

    def reset(self):
        self.ratio = 1
        self.ivmax = self.vmax * self.ipmm * self.ratio
        self.iamax = self.amax * self.ipmm * self.ratio

        # current controller state
        self._headx = self.ibound[0]
        self._heady = self.ibound[1]
        self._vx = 0.0
        self._vy = 0.0
        self._v = 0.0
        self._a = 0.0
        self._power = 0
        self._led = False

        # current physical state 
        self._head_err = [0, 0]
        self._head_actual = [self._headx, self._heady] 

        self.time = time.time()
        self.timestep = 0.01

        self.movedone = True
        self.iter = 0

        # current request
        self._destx = 0
        self._desty = 0
        self._feed = 0

        self.fifo = list()

    def turbo(self, ratio):
        self.ratio = ratio
        self.ivmax = self.vmax * self.ipmm * self.ratio
        self.iamax = self.amax * self.ipmm * self.ratio

    def load_gcode(self, gcode):

        pass

    def add_move(self, x, y, feed, power, led):
        #                  mm mm mm/sec pct bool
        self.fifo.append([x, y, feed, power, led])

    def exec_program(self):
        while len(self.fifo) > 0:
            
            self.exec_move(self.fifo.pop(0))

    def exec_move(self, x, y, feed, power, led):
        if not self.movedone:
            raise Exception("tried to execute a new move but machine is busy")

        self.movedone = False
        print("exec move",  x, y, feed, power, led)

        feed *= self.ratio

        self._destx = int(x*self.ipmm)
        self._desty = int(y*self.ipmm)
        self._feed = feed
        self._power = power
        self._led = led

        self._ifeed = self._feed * self.ipmm
        self.time = time.time()

    def start(self):
        if self.movedone and len(self.fifo) > 0:
            self.movedone = False

    def compute_frame(self, time):
        if self.movedone:
            # nothing to do, jump to the present
            self.time = time
            self.power = 0
        else:
            # Animate the move up to the request time
            # Pull moves out of the fifo as reqiured
            t = self.time
            while t < time:
                t += self.timestep
                self._do_step()
                if self.movedone and len(self.fifo) > 0:
                    self.exec_move(*self.fifo.pop(0))
                self.time = t

        return (self._head_actual[0]/self.ipmm,
                self._head_actual[1]/self.ipmm,
                self._power,
                self._led)


    def _do_step(self):
        destx, desty = self._destx, self._desty
        x, y  = self._headx, self._heady
        vx, vy  = self._vx, self._vy

        tstep = self.timestep
        self.iter += 1

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
                dvx = dx/dtg * self._ifeed
                dvy = dy/dtg * self._ifeed
                ax = (dvx - vx) / tstep
                ay = (dvy - vy) / tstep
                if self.debug: print("  cruise  ", dvx, dvy, self._ifeed, ax, ay)
                ax, ay = Animator.vector_limit(ax, ay, self.iamax)

            else:
                # pick accel to stop at dtg
                if dtg / tstep > v:
                    a = 0.5 * v * v / dtg
                    #a = max(min(a, self.iamax), -self.iamax)
                    ax = -a * dx/dtg
                    ay = -a * dy/dtg
                    if self.debug: print("  target  ", self._ifeed, ax, ay)
                else: 
                    ax = 0
                    ay = 0
                    vx = dx / tstep
                    vy = dy / tstep
                    if self.debug: print("  finish  ", self._ifeed, vx, ay)

        vx = vx + ax * tstep
        vy = vy + ay * tstep
        vx, vy = Animator.vector_limit(vx, vy, self.ivmax)

        x += (vx * tstep)
        y += (vy * tstep)

        xerr, yerr = self._head_err
        xa, ya = self._head_actual
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

        self._head_err = [xerr, yerr]
        self._head_actual = [xa, ya]
        self._a = a
        self._v = v
        self._vx = vx
        self._vy = vy
        self._headx = x
        self._heady = y

        if self.debug: print(f'i = {self.iter:4d} x = {x:6.2f} y = {y:6.2f}  vx = {vx:5.2f} vy = {vy:5.2f} v = {v:5.2f} dtg = {dtg:0.1f}   dts = {dts:0.1f} dx = {dx:0.1f} dy = {dy:0.1f} ax = {ax:0.1f} ay = {ay:0.1f}')

    @staticmethod
    def vector_limit(x, y, limit):
        m = math.sqrt(x*x+y*y)
        if m > limit:
            x = x * limit / m
            y = y * limit / m
        return x, y


if __name__ == '__main__':

    anim = Animator(debug = True)
    anim.exec_move(10, 0, 50, 5, 0)

    t0 = time.time()
    x, y, power, led = anim.compute_frame(t0+0.5)

    anim.exec_move(20, 10, 50, 5, 0)
    t0 = time.time()
    x, y, power, led = anim.compute_frame(t0+0.5)

    anim.exec_move(0, 0, 50, 5, 0)
    t0 = time.time()
    x, y, power, led = anim.compute_frame(t0+1.5)

    ti = time.time()
    timeout = 10.3
    anim.exec_move(30, 20, 20, 5, 0)
    while anim.movedone == False and (ti-t0)<timeout:
       ti +=0.100
       x, y, power, led = anim.compute_frame(ti)

    ti = time.time()
    timeout = 10.3
    anim.exec_move(-10, -10, 20, 5, 0)
    while anim.movedone == False and (ti-t0)<timeout:
       ti +=0.100
       x, y, power, led = anim.compute_frame(ti)

