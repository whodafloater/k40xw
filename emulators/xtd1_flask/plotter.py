#!/usr/bin/env python3

import sys
if __name__ == '__main__':
    sys.path.append("../..")
    sys.path.append("../../src")
    print("sys.path =", sys.path)

import argparse
import textwrap
import os
import time
import re
import math
from dataclasses import dataclass, field

import tkinter as tk
import tkinter.ttk as ttk

import emulators.tklib.tklib as tklib
from xtd1 import XTD1
import animator

def point_scale(xy, scale, offset=None):
    if offset==None:
        if len(xy) == 4:
            return (xy[0]*scale, xy[1]*scale, xy[2]*scale, xy[3]*scale)
        if len(xy) == 2:
            return (xy[0]*scale, xy[1]*scale)
    else:
        if len(xy) == 4:
            return (xy[0]*scale+offset[0], xy[1]*scale+offset[1], xy[2]*scale+offset[0], xy[3]*scale+offset[1])
        if len(xy) == 2:
            return (xy[0]*scale+offset[0], xy[1]*scale+offset[1])

@dataclass()
class Path:
    cids: list
    pix_per_mm:  float
    power:  int
    feed:   int
    cross:  int
    points: list
    scale:  float

class Gcode():
    def __init__(self):
        pass

class SketchControl(tklib.Frame):
    def __init__(self, debug=False, plotter=None, *args, **kwargs):
        super().__init__(*args, **kwargs)     # tklib.Frame place this with App.stack


        self.gcode = list()
        self.gcodestr = ''
        self.gcodeb = b''
        self.paths = list()
        self.spindle_power_scale = 10
        self.plotter = plotter

        self.color = tk.StringVar(value='red', name = 'color')
        self.power = tk.IntVar(value=6, name='Laser Power')
        self.feed =  tk.IntVar(value=600, name='Feed Rate')
        self.cross = tk.BooleanVar(value=False, name='LED cross')

        tklib.Label("Sketch Control")
        tklib.Frame()

        #cb = tklib.Checkbutton(items=[self.power, self.cross])
        #tklib.Entry(self.color)
        #tklib.Entry(self.power)
        #tklib.Entry(self.feed)
        #tklib.Entry(self.cross)

        tklib.EntryTable(var = [self.color, self.power, self.feed, self.cross],
                         units = [None, "pct", "mm/min", None],
                         cmd = self.table_callback,
                         entry_width = 6
                        )

        tklib.Button(text="Generate G Code", cmd=self.generate_gcode).pack_configure(pady=15)

        #real = tklib.Frame(name='realtool')
        real = tklib.LabelFrame(text='XTool D1', name='realtool').pack_configure(pady=15)
        self.realhost = tk.StringVar(value='192.168.0.106', name='real_host')
        self.realport = tk.StringVar(value='8080', name='real_port')
        tklib.EntryTable(var = [self.realhost, self.realport], cmd = self.host_cb, entry_width=15)
        tklib.Frame()
        tklib.Label(text="Upload").pack_configure(side='top')
        tklib.Frame()
        tklib.Button(text="frame", cmd=self.real_upload_framing_gcode).pack_configure(side='left')
        tklib.Button(text="burn",  cmd=self.real_upload_cutting_gcode).pack_configure(side='left')
        tklib.Pop()
        tklib.Pop()

        tklib.Pop(real)

        #sim = tklib.Frame(name='simtool')
        sim = tklib.LabelFrame(text='Emulator', name='simtool').pack_configure(pady=15)
        self.simhost = tk.StringVar(value='127.0.0.1', name='sim_host')
        self.simport = tk.StringVar(value='8080', name='sim_port')
        tklib.EntryTable(var = [self.simhost, self.simport], cmd = self.host_cb, entry_width=15)
        tklib.Frame()
        tklib.Label(text="Upload").pack_configure(side='top')
        tklib.Frame()
        tklib.Button(text="upload frame", cmd=self.sim_upload_framing_gcode).pack_configure(side='left')
        tklib.Button(text="upload burn",  cmd=self.sim_upload_cutting_gcode).pack_configure(side='left')
        tklib.Pop()
        tklib.Pop()
        tklib.Pop(sim)

        tklib.Pop()

    def generate_gcode(self):
        self.plotter.export_gcode()


    def sim_connect(self):
        tool = XTD1()
        tool.IP = self.simhost.get()
        tool.port = self.simport.get()
        return tool

    def real_connect(self):
        tool = XTD1()
        tool.IP = self.realhost.get()
        tool.port = self.realport.get()
        return tool

    def sim_upload_framing_gcode(self):
        self.sim_connect().framefile_upload(gcode=self.gcodeb)

    def sim_upload_cutting_gcode(self):
        self.sim_connect().cutfile_upload(gcode=self.gcodeb)

    def real_upload_framing_gcode(self):
        self.real_connect().framefile_upload(gcode=self.gcodeb)

    def real_upload_cutting_gcode(self):
        self.real_connect().cutfile_upload(gcode=self.gcodeb)

    def host_cb(self, source, event):
        print(f'table_callback from:{source}\n     event:{event}') 
        print(f'table_callback  variable: {source["textvariable"]}')

    def cb_callback(self):
        print(f'{__name__}: {cb.selection}') 

    def table_callback(self, source, event):
        #tklib.whatami(tklib.App.root, source)
        #tklib.whatami(None, source)
        #print(source.configure())
        print(f'table_callback from:{source}\n     event:{event}') 
        print(f'table_callback  variable: {source["textvariable"]}')
        #print(f'table_callback     value: {source.Variable.get()}') 

    def add_path(self, cids=None, pix_per_mm=1):
        """ Populate a new Path with a list of canvas id's.
            Append it to the sketch paths[].

            cids -- list of canvas id
            pix_per_mm -- pixels per mm during mouse capture. This indicates capture resolution.
        """
        if cids == None: return
        self.paths.append( Path( cids = cids,
                                 points = list(),
                                 power = self.power.get(),
                                 feed = self.feed.get(),
                                 cross = self.cross.get(),
                                 pix_per_mm = pix_per_mm,
                                 scale = 0
                                )
                         )

    def clear_paths(self):
        self.paths = list()

    def retrieve_points_from_canvas(self, canvas, mapfn):
        """
            canvas -- where to get the data
            scale -- scale factor. world/canvas
        """
        for p in self.paths:
            if len(p.cids) == 0: continue
            segment = None
            lastseg = None
            print(f'next path')
            p.points = list()
            for cid in p.cids:
                lastseg = segment
                segment = canvas.coords(cid)
                print(f'last {lastseg}  current{segment}')
                if lastseg != None:
                   # make sure its continuous
                   assert(segment[0] == lastseg[2])
                   assert(segment[1] == lastseg[3])
                x, y = mapfn(segment[0], segment[1])
                p.points.append((x,y))

            x, y = mapfn(segment[2], segment[3])
            p.points.append((x,y))


    def gcode_from_paths(self):
        self.gcode = []
        self.gcodestr = ''
        self.gcodeb = b''

        # defaults
        feed =  10 * 60   # mm/min
        rapid = 3000      # mm/min
        power = 5 * self.spindle_power_scale

        gcode = []
        gcode.append(f'M17 S1\n')
        gcode.append(f'M205 X426 Y403\n')  # file uploads do not work with out this
        gcode.append(f'M101\n')
        gcode.append(f'G90\n')
        gcode.append(f'G92 X0 Y0\n')
        gcode.append(f'G0 F{rapid}\n')
        gcode.append(f'G1 F{feed}\n')
        gcode.append(f'G1 S{power}\n')

        current_feed = feed
        current_power = power
        ledon = False

        for p in self.paths:
            print(p)
            rapid = True

            feed = p.feed
            power = p.power * self.spindle_power_scale

            for x, y in p.points:
                if rapid:
                    gc = f'G0 X{x:0.2f} Y{y:0.2f}'
                    rapid = False
                else:
                    gc = f'G1 X{x:0.2f} Y{y:0.2f}'
                    if feed != current_feed:
                        gc = gc + f' F{feed:.0f}'
                        current_feed = feed

                    if power != current_power:
                        gc = gc + f' S{power:.0f}'
                        current_power = power
                print(gc)
                gcode.append(gc + '\n')

        x,y = 0,0
        gcode.append(f'G0 X{x:0.3f} Y{y:0.3f}\n')
        gcode.append(f'M18\n')

        self.gcode = gcode
        self.gcodestr = ''.join(gcode)
        self.gcodeb = ''.join(gcode).encode(encoding='utf-8')

        print("gcode:\n" + self.gcodestr)
 
        return gcode


class Plotter(tklib.Frame):
    def __init__(self, debug=False, enable_sketcher=True, width=400, height=300, *args, **kwargs):
        super().__init__(*args, **kwargs)     # tklib.Frame place this with App.stack
        #super().__init__(parent, *args, **kwargs)


        self.lastmouse = None
        self.startup = True

        self.debug = debug
        self.c = None
        self.reference_id = None
        self.nav = None
        self.skctrl = None
        self.ch = 0
        self.cw = 0
        self.enable_sketcher = enable_sketcher

        self.bed = (0,0, 426, 403)  # mm, limits of the head travel
        self.head = (-25,-35, 25, 25)  # mm
        self.carrige = (-51, -88, 493, -45)  # mm
        self.frame   = (-53, -90, 495, 430)  # mm
        self.laser_offset   = (0, 0)  # mm
        self.laser_size   = 3  # mm
        self.led_offset   = (-17, -1)  # mm
        self.led_size   = 10  # mm

        self.anim = animator.Animator(self.bed)
        self.headpos = [0,0]
        #self.headpos = self.anim.compute_frame(time.time())

        self.reference = self.frame
        self.reference = Plotter.box_grow(self.frame, 10)

        # self.zoom is pixels per world unit, as in pixels per mm
        # it keeps track of accumulated canvas scaling.
        # It only purpose is put a limit on the max zoom
        # based on requested window size
        self.zoom = self.scale_to_fit(self.reference, (0, 0, width, height))
        self.min_world_view = 0.1  # mm

        self.plotterpad = 0  # pixel
        self.canvpad = 0  # pixel

        self.__delta = 1.3  # zoom magnitude

        # initial size request for canvas
        pixel_per_mm = 1
        bx1, by1, bx2, by2 = self.reference
        w = (bx2-bx1) * pixel_per_mm
        h = (by2-by1) * pixel_per_mm
        print(f'initiale canvase size request {w,h}')

        self.xy_readout = tk.StringVar()
        # put widgets in self. We are the new frame


        self.pack_configure(expand=True, fill='both')
        plotframe = tklib.Frame(name='machine')
        plotframe.pack_configure(side='left', expand=True) 
        self.create_widgets(plotframe, width=w, height=h)
        self.create_nav(self.nav)
        tklib.Pop(plotframe)

        if enable_sketcher:
           self.sk = SketchControl(plotter = self)
           self.sk.pack_configure(side='right', fill='y') 
           tklib.Pop(self.sk)

        self.c.create_rectangle(self.bed,     tags='bed',     outline='gray')
        self.c.create_rectangle(self.head,    tags='head',    outline='dark gray')
        self.c.create_rectangle(self.carrige, tags='carrige', outline='dark gray')
        self.c.create_rectangle(self.frame,   tags='frame',   outline='black', width=2)

        self.c.create_oval(
            point_scale(self.laser_offset, 1, (-self.laser_size, -self.laser_size)),
            point_scale(self.laser_offset, 1, ( self.laser_size,  self.laser_size)),
            tags='laser', outline='black', fill='gray', width=2)

        self.c.create_line(point_scale(self.led_offset, 1, (self.led_size,0)),
                           point_scale(self.led_offset, 1, (-self.led_size,0)),
                           tags='led', fill='red', width=2)

        self.c.create_line(point_scale(self.led_offset, 1, (0,-self.led_size)),
                           point_scale(self.led_offset, 1, (0,self.led_size)),
                           tags='led', fill='red', width=2)

        # Put image into reference rectangle and use it to set proper coordinates to the image
        # The reference essentially dirves the scroll bar position and size
        self.reference_id = self.c.create_rectangle(self.reference, width=0)
        self.__min_side = Plotter.box_min_side(self.c.coords(self.reference_id))

        self.color = ''
        self.setColor('black')

        self.c.bind('<Configure>', self.on_configure)
        self.c.bind("<Button-1>", self.xy)
        self.c.bind("<B1-Motion>", self.addLine)
        self.c.bind("<B1-ButtonRelease>", self.doneStroke)

        self.c.bind('<ButtonPress-3>', self.__on_b3_press)  # canvas mark
        self.c.bind("<B3-Motion>",     self.__on_b3_motion) # canvas drag, dashboard
        self.c.bind('<Motion>',        self.__on_motion)    # dashboard

        # from junkyard
        self.canvas.bind('<MouseWheel>', self.__wheel)  # zoom for Windows and MacOS, but not Linux
        self.canvas.bind('<Button-5>',   self.__wheel)  # zoom for Linux, wheel scroll down
        self.canvas.bind('<Button-4>',   self.__wheel)  # zoom for Linux, wheel scroll up

        if self.debug:
           self._update_converters()
           self.test()

        self.tick()
        self.anim.program_move(200, 100, 50, 5, 0)
        # wait for the configure event to do anything with the canvas
        return

    def tick(self):
        self.headpos[0], self.headpos[1], power, led = self.anim.compute_frame(time.time())
        if not self.startup:
            self.move_carrige(*self.headpos, power, led)
            pass
        self.after(30, self.tick)
        #self.after(1000, self.tick)

    def move_carrige(self, wx, wy, power, led):
        chx, chy = self.fwc(wx + self.head[0], wy + self.head[1])
        ccx, ccy = self.fwc(self.carrige[0],   wy + self.carrige[1])

        cledx, cledy = self.fwc(wx - self.led_size + self.led_offset[0],
                                wy - self.led_size + self.led_offset[1])


        self.c.moveto('head',    chx, chy)
        self.c.moveto('carrige', ccx, ccy)
        self.c.moveto('led',     cledx, cledy)

        if led:
            self.c.itemconfigure('led', fill='red')
        else:
            self.c.itemconfigure('led', fill='gray')

        if power > 0:
            self.c.itemconfigure('laser', fill='orange')
        else:
            self.c.itemconfigure('laser', fill='gray')

        clasx, clasy = self.fwc(wx - self.laser_size + self.laser_offset[0],
                                wy - self.laser_size + self.laser_offset[1])
        self.c.moveto('laser',   clasx, clasy)

        

    def test(self):
        if self.c == None: return
        self.cw = self.c.winfo_width()
        self.ch = self.c.winfo_height()
        xy = (0, 0)
        x, y = xy
        wxy = self.pixel_to_world(xy)
        print(f' 0, 0 --> world {wxy}')

        f = self.map_func((0,0,10,10), (30,20,50,100))
        assert(f(0, 0) == (30, 20))
        assert(f(10, 10) == (50, 100))

        return
        canvas_image = self.c.coords(self.reference_id)  # get image area
        pixel_image = self.canvas_to_pixel(canvas_image)
        scale = self.scale_to_fit(pixel_image, (0,0,self.cw,self.ch))
        print(f'self test  scale to fit = {scale}')

    def test_add_bed(self):
        pc = self.world_to_canvas(self.bed)
        print(f'add bed:  {self.bed}  {pc}')
        self.c.create_rectangle(pc, tags='test', outline='red')

    def __on_b3_press(self, e):
        self.c.scan_mark(e.x, e.y)

    def __on_b3_motion(self, e):
        self.c.scan_dragto(e.x, e.y, 1)
        self.update_readout(e)
        self.lastmouse = e
        #print(f'B3 motion  {e}')

    def __on_motion(self, e):
        self.update_readout(e)
        self.lastmouse = e

    def update_readout(self, e=None, xy=None):
        if e != None: 
            x,y = e.x, e.y
        elif xy != None:
            x,y = xy
        else:
            return
        wx, wy = self.pixel_to_world((x, y))
        #print(f'mouse world {wx:5.1f} {wy:5.1f}')
        #self.xy_readout.set(f'X: {wx:5.1f}  Y: {wy:5.1f}')
        self.xy_readout.set(f'pix: {x:4d} {y:4d}  X: {wx:5.1f}  Y: {wy:5.1f}')
        cx, cy = self.c.canvasx(0), self.c.canvasy(0)
        self.xy_readout.set(f'can: {cx:4.0f} {cy:4.0f}   pix: {x:4d} {y:4d}  X: {wx:5.1f}  Y: {wy:5.1f}')


    def create_widgets(self, parent, width=400, height=300):
        # nav and sketch control frames are created but not populated

        # Plot frame is grid packed with:
        #  | nav bar |         |
        #  | canvas  | scrolly |
        #  | scrollx |         |

        #f = tklib.Frame()
        f = parent
        f.pack_configure(fill='both', expand=True, padx=self.plotterpad, pady=self.plotterpad)  

        # how f will manage its children
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

        # scrolls get only what they need
        f.columnconfigure(1, weight=0)
        f.rowconfigure(2, weight=0)

        # stuff in f
        nav = tklib.Frame(name='nav')
        nav.grid(row=0, column=0, sticky='nswe')
        self.nav = nav
        # populate this one later
        tklib.Pop(nav)

        c = tk.Canvas(f, bg='powder blue', width=width, height=height, name='canvas')
        c.grid(row=1, column=0, sticky='nswe', padx=self.canvpad, pady=self.canvpad)
        self.c = c
        self.canvas = c

        sy = ttk.Scrollbar(f, orient=tk.VERTICAL, name='scrolly')
        sy.grid(row=1, column=1, sticky='nse')
        self.sy = sy

        sx = ttk.Scrollbar(f, orient=tk.HORIZONTAL, name='scrollx')
        sx.grid(row=2, column=0, sticky='swe')
        self.sx = sx

        # link the scrollbars to the canvas
        def canvas_xscrolled_cb(s1, s2):
            sx.set(s1, s2)
            self._update_converters()
            self.update_readout(self.lastmouse)

        def canvas_yscrolled_cb(s1, s2):
            sy.set(s1, s2)
            self._update_converters()
            self.update_readout(self.lastmouse)

        c.configure(xscrollcommand = canvas_xscrolled_cb)
        c.configure(yscrollcommand = canvas_yscrolled_cb)

        # The canvas updates the scroll bars length and position
        # set the callback function for the scrollbar to the xview, yview methods in the canvas
        sx.configure(command = c.xview)
        sy.configure(command = c.yview)
        return


 
    def create_nav(self, frame):
        tklib.Push(frame)
        home = tklib.Button(text="zoom reset", cmd=self.reset_zoom, name='reset')
        home.pack_configure(side='left')

        test = tklib.Button(text="Clear", cmd=self.clear_sketch, name='clear')
        test.pack_configure(side='left')

        #test = tklib.Button(text="Gen GCode", cmd=self.export_gcode)
        #test.pack_configure(side='left')


        test = tklib.Button(text="add test R", cmd=self.test_add_bed)
        test.pack_configure(side='left')

        #tklib.Button(text="update conv", cmd=self._update_converters
        #   ).pack_configure(side='left')


        status = tklib.Label(text="status", name='status')
        status.pack_configure(side='left')

        xy = tklib.Label(text="0,0", textvariable=self.xy_readout, name='readout')
        xy.pack_configure(side='right')
        tklib.Pop(frame)


    @staticmethod
    def scaled_tuple(xy, scale):
        if len(xy) == 4:
           return (xy[0]*scale, xy[1]*scale, xy[2]*scale, xy[3]*scale)
        if len(xy) == 2:
           return (xy[0]*scale, xy[1]*scale)


    @staticmethod
    def scale_to_fit(box, target):
        xscale = (target[2] - target[0]) / (box[2] - box[0])
        yscale = (target[3] - target[1]) / (box[3] - box[1])
        return min(xscale, yscale)

    def reset_zoom(self, event=None):
        """ 
            Move everything on the canvas to position reference area
            at window upper left
            Scale to fit reference area in the window
        """
        ref_can = self.c.coords(self.reference_id)
        x1 = ref_can[0]
        y1 = ref_can[1]
        x2 = self.c.canvasx(0)
        y2 = self.c.canvasy(0)
        dx = x2 - x1
        dy = y2 - y1

        self.c.move('all', dx, dy)

        assert(self.c.canvasx(self.cw)-self.c.canvasx(0) == self.cw)
        assert(self.c.canvasx(self.ch)-self.c.canvasx(0) == self.ch)
        print(f' window width pixels?  {self.c.canvasx(self.cw)-self.c.canvasx(0)}')
        print(f' window height pixels? {self.c.canvasy(self.ch)-self.c.canvasy(0)}')
        self.cw = self.c.winfo_width()
        self.ch = self.c.winfo_height()
        print(f' window pixels {self.cw, self.ch}')

        scale = self.scale_to_fit(ref_can, (0, 0, self.cw, self.ch))
        self.zoom *= scale

        self.c.scale('all', x2, y2, scale, scale)
        self._update_converters()
        self._set_scrollregion()
        return

    def clear_sketch(self, event=None):
        self.c.delete('sketch')
        if self.enable_sketcher:
            self.sk.clear_paths()

    def export_gcode(self, event=None):
        print('export_gcode')

        self._update_converters()
        if self.enable_sketcher:
            self.sk.retrieve_points_from_canvas(self.c, self.fcw)
            self.sk.gcode_from_paths()


    def on_configure(self, e):
        #print(f'canvas configure: {e}')
        if self.startup:
           self.reset_zoom()
           self.startup = False
        self.ch = e.height
        self.cw = e.width
        self._update_converters()


    def xview(self, e):
        print(f'xview: {e} {sx}')
        pass

    def yview(self, e):
        print(f'yview: {e} {sy}')
        pass

    def xy(self, event):
        print(f'xy: {event}')
        self.lastx, self.lasty = self.c.canvasx(event.x), self.c.canvasy(event.y)

    def addLine(self, event):
        x2, y2 = self.c.canvasx(event.x), self.c.canvasy(event.y)
        x1, y1 = self.lastx, self.lasty
        d = math.dist((x1,y1), (x2,y2)) / self.zoom
        t = time.time()
        if t < 0.300 and d < 4: return
        if d < 0.3: return

        print(f'line {d} {x2,y2} {event}')
        self.c.create_line((self.lastx, self.lasty, x2, y2), fill=self.color, width=5, tags=['currentline','sketch'])
        self.lastx, self.lasty = x2, y2
        self.lastime = time.time()

    def doneStroke(self, event):
        
        print(f' done stroke:{event}')
        ids = self.c.find_withtag('currentline')
        #self.c.itemconfigure(ids, width=1)        
        self.c.itemconfigure('currentline', width=1)        
        #self.c.dtag(ids, 'currentline')
        for id in ids:
            self.c.dtag(id, 'currentline')
            
        print(f' tags for id:{ids}')
        #print(f' tags for id:{id}   {self.c.gettags(id)} ')
        self.sk.add_path(cids=ids, pix_per_mm = self.zoom)

    def setColor(self, newcolor):
        self.color = newcolor
        self.c.dtag('all', 'paletteSelected')
        self.c.itemconfigure('palette', outline='white')
        self.c.addtag('paletteSelected', 'withtag', 'palette%s' % self.color)
        self.c.itemconfigure('paletteSelected', outline='#999999')


    @staticmethod
    def map_func(a, b, c=None, name=None):
        """
            Return a function that maps x,y in 'a' space to 'b' space
            a and b are rectangle coords: (x1, y1, x2, y2)
        """
        xs = (b[2] - b[0]) / (a[2] - a[0])
        ys = (b[3] - b[1]) / (a[3] - a[1])
        xo =  b[0] - a[0] * xs
        yo =  b[1] - a[1] * ys

        if c!= None:
           c.append([xs, ys, xo, yo])
        if name !=None:
           #print(f'        {name:10s} ({Plotter.box_str(a)})  ->  ({Plotter.box_str(b)})')
           pass

        return lambda x, y: (x * xs + xo, y * ys + yo)

    def _update_converters(self):
        """
           We have some coord systems
              world in mm,in etc
              canvas floating point pixels
              window integer pixels

           Canvas coords have the same scaling as the window pixels.
           A 10x10 rect in canvas coords is a 10x10 box in window
           pixels.

           canvas.coords() returns data in screen pixel units.
           They are floats, with fractional values. They have
           an offset. The offset can be obtained with
           canvas.canvasx() and canvas.canvasy(). both return
           floating point canavs coords.


           Since we know the main reference size in world units
           we can use that to map pixel units to world units.
           This mapping changes with window resize, pan and zoom
        """

        # call this after window configures and pan and scale operationss
        self.cw = self.c.winfo_width()
        self.ch = self.c.winfo_height()

        if self.debug:
           print(f' canvas UL? {self.c.canvasx(0)} {self.c.canvasy(0)}')
           print(f' canvas LR? {self.c.canvasx(self.cw)} {self.c.canvasy(self.ch)}')

           print(f' window width pixels?  {self.c.canvasx(self.cw)-self.c.canvasx(0)}')
           print(f' window height pixels? {self.c.canvasy(self.ch)-self.c.canvasy(0)}')

           # yes it is so
           assert(self.c.canvasx(self.cw)-self.c.canvasx(0) == self.cw)
           assert(self.c.canvasx(self.ch)-self.c.canvasx(0) == self.ch)

        # get reference area in canvas units
        # chicken agg thing. 
        if self.reference_id == None:
           ref_can = (0, 0, self.cw, self.ch)
        else:
           ref_can = self.c.coords(self.reference_id)

        self.fwc = self.map_func(self.reference, ref_can)
        self.fcw = self.map_func(ref_can, self.reference)

        # get reference area in window pixel units
        can_offset = (self.c.canvasx(0), self.c.canvasy(0))
        ref_pix = (ref_can[0] - can_offset[0],
                   ref_can[1] - can_offset[1],
                   ref_can[2] - can_offset[0],
                   ref_can[3] - can_offset[1])

        cpw = []
        self.fpw = self.map_func(ref_pix, self.reference, cpw, name='cpw')
        self.fwp = self.map_func(self.reference, ref_pix)

        self.zoom = 1 / cpw[0][0]
        #print(f'zoom = {self.zoom:.0f} pixels per mm   cpw={cpw}')

        # get visible area of the canvas in canvas pix units
        win_can = self.canvas_vis_box()
        # get visible area of the canvas in window pixel units
        win_pix = (0, 0, self.c.winfo_width(), self.c.winfo_height())

        self.fcp = self.map_func(win_can, win_pix)
        self.fpc = self.map_func(win_pix, win_can)

        #print(f'    update_converters:   refer   world:{self.box_str(self.reference)}')
        #print(f'    update_converters:   refer  canvas:{self.box_str(ref_can)}')
        #print(f'    update_converters:   win       pix:{self.box_str(win_pix)}')
        #print(f'    update_converters:   win    canvas:{self.box_str(win_can)}')
        #print(f'    update_converters:   pix to world coeff = {cpw}')


    def canvas_to_pixel(self, xy):
        if len(xy) == 2: return self.fcp(xy[0], xy[1])
        if len(xy) == 4: return self.fcp(xy[0], xy[1]), self.fcp(xy[2], xy[3])
        raise Exception('expect 1 or 2 x,y points')
         
    def pixel_to_world(self, xy):
        if len(xy) == 2: return self.fpw(xy[0], xy[1])
        if len(xy) == 4: return self.fpw(xy[0], xy[1]), self.fpw(xy[2], xy[3])
        raise Exception('expect 1 or 2 x,y points')

    def world_to_canvas(self, xy):
        if len(xy) == 2: return self.fwc(xy[0], xy[1])
        if len(xy) == 4: return self.fwc(xy[0], xy[1]), self.fwc(xy[2], xy[3])
        raise Exception('expect 1 or 2 x,y points')

    def canvas_vis_box(self):
        """ canvas units at the visible area UL and LR """
        bc = (self.c.canvasx(0),  # get visible area of the canvas
              self.c.canvasy(0),
              self.c.canvasx(self.c.winfo_width()),
              self.c.canvasy(self.c.winfo_height()))
        return bc

    def _set_scrollregion(self):
        # scrollregion inside the canvas visible window:
        #    scroll bar slider turns OFF region annunciator bar
        #    dragto is limited by the scrollregion.
        #    scrollregion cannot be dragged outside the visible canvas
        #
        # scrollregion bigger than the visible window: 
        #    scroll bar slider turns ON region annunciator bar
        #    dragto is limited by the scroll region,
        #    limits are faithful to the region annunciator bar.
        #    Size of the bar indicates how zoomed we are

        # get image area, integer pixel units, round in
        image_box = self.box_round_inward( self.c.coords(self.reference_id) )
        # this grow required to get the region bars to turn off when
        # the reference box is zoomed to the corners
        image_box = self.box_grow( image_box, -2 )

        self.c.configure(scrollregion=image_box) 
        return

    # from junkyard
    def outside(self, x, y):
        """ Checks if the point (x,y) is outside the image area """
        bbox = self.canvas.coords(self.reference_id)  # get image area
        if bbox[0] < x < bbox[2] and bbox[1] < y < bbox[3]:
            return False  # point (x,y) is inside the image area
        else:
            return True  # point (x,y) is outside the image area

    # from junkyard
    def __wheel(self, event):
        """ Zoom with mouse wheel """
        x = self.canvas.canvasx(event.x)  # get coordinates of the event on the canvas
        y = self.canvas.canvasy(event.y)
        if self.outside(x, y): return  # zoom only inside image area
        scale = 1.0
        # Respond to Linux (event.num) or Windows (event.delta) wheel event
        if event.num == 5 or event.delta == -120:  # scroll down, zoom out, smaller
            if round(self.__min_side * self.zoom) < 30: return  # image is less than 30 pixels
            self.zoom /= self.__delta
            scale        /= self.__delta
        if event.num == 4 or event.delta == 120:  # scroll up, zoom in, bigger
            i = float(min(self.canvas.winfo_width(), self.canvas.winfo_height()) >> 1)
            if i < self.zoom * self.min_world_view: return 
            self.zoom *= self.__delta
            scale        *= self.__delta
        self.canvas.scale('all', x, y, scale, scale)  # rescale all objects
        self._update_converters()
        # Redraw some figures before showing image on the screen
        #self.redraw_figures()  # method for child classes
        self._set_scrollregion()

    @staticmethod
    def box_min_side(bbox):
        """ smaller side of a bounding box """
        return min(bbox[2]-bbox[0], bbox[3]-bbox[1])

    @staticmethod
    def box_grow(b, d):
        return (b[0]-d, b[1]-d, b[2]+d, b[3]+d)

    @staticmethod
    def box_round_outward(b):
        return [math.floor(b[0]), math.floor(b[1]),
                math.ceil(b[2]),  math.ceil(b[3])]

    @staticmethod
    def box_round_inward(b):
        return [math.ceil(b[0]), math.ceil(b[1]),
                math.floor(b[2]), math.floor(b[3])]

    @staticmethod
    def box_around_both(a, b):
        return [min(a[0], b[0]), min(a[1], b[1]),
                max(a[2], b[2]), max(a[3], b[3]) ]

    @staticmethod
    def box_expand_to(a, b):
        a = list(a)
        if b[0] < a[0]:
            a[0] = b[0]
        if b[1] < a[1]:
            a[1] = b[1]
        if b[2] > a[2]:
            a[2] = b[2]
        if b[3] > a[3]:
            a[3] = b[3]
        return a

    @staticmethod
    def box_str(b):
        return f'{b[0]:7.1f} {b[1]:7.1f}  {b[2]:7.1f} {b[3]:7.1f}'



def plotter_test(args):
    debug = args['debug']
    app = tklib.App('plotter test', debug=debug)

    Plotter(debug=debug)

    tklib.report_stack()

    if args['widgets']:
        w = tklib.App.stack[0]
        tklib.report_tree(w)
        exit(0)

    app.run()

if __name__ == '__main__':


    epilog = textwrap.dedent("""\
        That's all folks!
        """)

    parser = argparse.ArgumentParser(
       description='plotter, sketcher, motion simulator',
       formatter_class=argparse.RawDescriptionHelpFormatter,
       epilog = epilog
      )

    parser.add_argument('-d', "--debug", required=False, action='store_true',
                        help='debug flag')

    parser.add_argument('-w', "--widgets", required=False, action='store_true',
                        help='report widget hierarchy and exit')

    argu = parser.parse_args()
    args = vars(argu)

    print(type(argu), argu)
    print(type(args), args)

    plotter_test(args)
    exit(0)

    app = tklib.App('plotter test')

    tklib.Label(text = 'tcllib Demo',
        relief='raised', pad=3, anchor='center', background='light green'
       ).pack_configure(fill='x')


    tklib.Frame(borderwidth=5, relief='sunken').pack_configure(expand=True, fill='both')

    Plotter()
    #tklib.Canvas(bg='powder blue').pack_configure(side='right', expand=True, fill='both')

    tklib.Text(text='hello world!', width=20, height=10).pack_configure(side='left', fill='y')
    tklib.App.stack.pop()

    tklib.Frame()
    tklib.Button(text='One').grid_configure(row=0, column=0)
    tklib.Button(text='Two').grid_configure(row=0, column=1)
    tklib.Button(text='Three').grid_configure(row=0, column=2)

    tklib.App.stack.pop()
    app.run()

