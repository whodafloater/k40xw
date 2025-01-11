#!/usr/bin/env python3


#import sys
import os
import re
import math
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog, colorchooser

from PIL import Image, ImageTk, ImageGrab
import random

import tklib
import time
import ecoords
#import xtool_lib as xtd1

from dataclasses import dataclass, field


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
    points: list
    power:  int
    feed:   int
    cross:  int

class Gcode():
    def __init__(self):
        pass

class SketchControl(tklib.Frame):
    def __init__(self, debug=False, *args, **kwargs):
        super().__init__(*args, **kwargs)     # tklib.Frame place this with App.stack

        self.color = tk.StringVar(value='red', name = 'color')
        self.power = tk.IntVar(value=5, name='Laser Power, %')
        self.feed =  tk.IntVar(value=3000, name='Feed Rate, mm/min')
        self.cross = tk.BooleanVar(value=False, name='LED cross')

        tklib.Label("Sketch Control")
        cb = tklib.Checkbutton(items=[self.power, self.cross])

        tklib.Frame()
        tklib.Entry(self.color)
        tklib.Entry(self.power)
        tklib.Entry(self.feed)
        tklib.Entry(self.cross)

        tklib.EntryTable(var = [self.color, self.power, self.feed, self.cross],
                         units = [None, "pct", "mm/min", None],
                         cmd = self.table_callback
                        )
        tklib.Pop()


    def cb_callback(self):
        print(f'{__name__}: {cb.selection}') 

    def table_callback(self, source, event):
        #tklib.whatami(tklib.App.root, source)
        #tklib.whatami(None, source)
        #print(source.configure())
        print(f'table_callback from:{source}\n     event:{event}') 
        print(f'table_callback  variable: {source["textvariable"]}')
        #print(f'table_callback     value: {source.Variable.get()}') 

class Plotter(tklib.Frame):
    def __init__(self, parent, debug=False, width=400, height=300, *args, **kwargs):
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

        self.platten = (0,0, 426, 403)  # mm
        self.head = (-25,-35, 25, 25)  # mm
        self.carrige = (-51, -88, 493, -45)  # mm
        self.frame   = (-53, -90, 495, 430)  # mm
        self.led   = (-17, -1)  # mm

        self.reference = self.frame
        self.reference = Plotter.box_grow(self.frame, 10)

        # self.zoom is pixels per world unit, as in pixels per mm
        # it keeps track of accumulated canvas scaling.
        # It only purpose is put a limit on the max zoom
        # based on requested window size
        self.zoom = self.scale_to_fit(self.reference, (0, 0, width, height))
        self.min_world_view = 0.1  # mm

        self.plotterpad = 10  # pixel
        self.canvpad = 10  # pixel

        self.__delta = 1.3  # zoom magnitude

        # initial size request for canvas
        pixel_per_mm = 1
        bx1, by1, bx2, by2 = self.reference
        w = (bx2-bx1) * pixel_per_mm
        h = (by2-by1) * pixel_per_mm
        print(f'initiale canvase size request {w,h}')

        self.xy_readout = tk.StringVar()
        # put widgets in self. We are the new frame

        plotframe = tklib.Frame()
        plotframe.pack_configure(side='left') 
        self.create_widgets(plotframe, width=w, height=h)
        self.create_nav(self.nav)
        tklib.Pop(plotframe)

        #ctrl = tklib.Frame()
        #ctrl.pack_configure(side='right', fill='y') 
        #tklib.Label("sketch control")
        sk = SketchControl()
        sk.pack_configure(side='right', fill='y') 
        tklib.Pop(sk)

        #print(f'Plotter: {tklib.App.stack}')
        #self.create_sketch_ctrl(self.skctrl)
        #print(f'Plotter: {tklib.App.stack}')


        self.c.create_rectangle(self.platten, tags='platten', outline='gray')
        self.c.create_rectangle(self.head,    tags='head',    outline='dark gray')
        self.c.create_rectangle(self.carrige, tags='carrige', outline='dark gray')
        self.c.create_rectangle(self.frame,   tags='frame',   outline='black', width=2)

        self.c.create_line(point_scale(self.led, 1, (10,0)),
                           point_scale(self.led, 1, (-10,0)),
                           tags='led', fill='red', width=2)
        self.c.create_line(point_scale(self.led, 1, (0,-10)),
                           point_scale(self.led, 1, (0,10)),
                           tags='led', fill='red', width=2)

         
        # Put image into reference rectangle and use it to set proper coordinates to the image
        # The reference essentially dirves the scroll bar position and size
        self.reference_id = self.c.create_rectangle(self.reference, width=0)
        self.__min_side = Plotter.box_min_side(self.c.coords(self.reference_id))

        self._update_converters()
        self.test()

        #self.machine_tags = ['platten', 'head', 'carrige', 'frame']

        #self.c.scale(self.machine_tags, 0, 0, self.scale, self.scale)

        #self.c.scale('head', 0, 0, self.scale, self.scale)
        #self.c.scale('platten', 0, 0, self.scale, self.scale)
        #self.c.scale('carrige', 0, 0, self.scale, self.scale)
        #self.c.scale('frame', 0, 0, self.scale, self.scale)
        #self.c.scale('led', 0, 0, self.scale, self.scale)


        self.color = ''
        self.setColor('black')

        self.c.bind('<Configure>', self.configure)
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


        # wait for the configure event to do anything with the canvas
        # Thats when we get an actual canvas size from the packers
        #self.update_idletasks()
        #self._update_converters()
        #self.reset_zoom()
        #self.c.update()
        #self.reset_zoom()
        #self.c.update()
        #self._set_scrollregion()
        #self.update_readout(xy=(0,0))
        #self.update()
        #self.lastime = time.time()

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

    def test_add_platten(self):
        pc = self.world_to_canvas(self.platten)
        print(f'add platten:  {self.platten}  {pc}')
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
        nav = tklib.Frame()
        nav.grid(row=0, column=0, sticky='nswe')
        self.nav = nav
        # populate this one later
        tklib.Pop(nav)

        c = tk.Canvas(f, bg='powder blue', width=width, height=height)
        c.grid(row=1, column=0, sticky='nswe', padx=self.canvpad, pady=self.canvpad)
        self.c = c
        self.canvas = c

        sy = ttk.Scrollbar(f, orient=tk.VERTICAL)
        sy.grid(row=1, column=1, sticky='nse')
        self.sy = sy

        sx = ttk.Scrollbar(f, orient=tk.HORIZONTAL)
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
        home = tklib.Button(text="zoom reset", cmd=self.reset_zoom)
        home.pack_configure(side='left')

        test = tklib.Button(text="Clear", cmd=self.clear_sketch)
        test.pack_configure(side='left')

        test = tklib.Button(text="Gen GCode", cmd=self.export_gcode)
        test.pack_configure(side='left')


        #test = tklib.Button(text="add test R", cmd=self.test_add_platten)
        #test.pack_configure(side='left')

        #tklib.Button(text="update conv", cmd=self._update_converters
        #   ).pack_configure(side='left')


        status = tklib.Label(text="status")
        status.pack_configure(side='left')

        xy = tklib.Label(text="0,0", textvariable=self.xy_readout)
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

    def export_gcode(self, event=None):
        print('export_gcode')

        d = self.c.find_withtag('sketch')
        print(d)
        lines = list()
        for id in d:
           lines.append(list(self.c.coords(id)))

        print(lines)

        #ec = ecoords.ECoord()
        #ec.make_ecoords(lines)

        #data = self.prep_ecoord_data(operation_type)
        #gc, segtime = self.xtd1.ecoord_to_gcode(data)


    def configure(self, e):
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
        d = math.dist((x1,y1), (x2,y2))
        t = time.time()
        if t < 0.300 and d < 4: return
         
        print(f'line {d}')
        self.c.create_line((self.lastx, self.lasty, x2, y2), fill=self.color, width=5, tags=['currentline','sketch'])
        self.lastx, self.lasty = x2, y2
        self.lastime = time.time()

    def doneStroke(self, event):
        ids = self.c.find_withtag('currentline')
        #self.c.itemconfigure(ids, width=1)        
        self.c.itemconfigure('currentline', width=1)        
        self.c.dtag('currentline', ids)
        #print(f' tags for id:{ids}')
        #print(f' tags for id:{id}   {self.c.gettags(id)} ')

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



def plotter_test(debug=False):
    app = tklib.App('plotter test', debug=debug)

    Plotter(tklib.App.stack[-1], debug=debug)

    app.run()

if __name__ == '__main__':

    plotter_test(debug=True)
    exit(0)

    app = tklib.App('plotter test')

    tklib.Label(text = 'tcllib Demo',
        relief='raised', pad=3, anchor='center', background='light green'
       ).pack_configure(fill='x')


    tklib.Frame(borderwidth=5, relief='sunken').pack_configure(expand=True, fill='both')

    Plotter(tklib.App.stack[-1])
    #tklib.Canvas(bg='powder blue').pack_configure(side='right', expand=True, fill='both')

    tklib.Text(text='hello world!', width=20, height=10).pack_configure(side='left', fill='y')
    tklib.App.stack.pop()

    tklib.Frame()
    tklib.Button(text='One').grid_configure(row=0, column=0)
    tklib.Button(text='Two').grid_configure(row=0, column=1)
    tklib.Button(text='Three').grid_configure(row=0, column=2)

    tklib.App.stack.pop()
    app.run()

