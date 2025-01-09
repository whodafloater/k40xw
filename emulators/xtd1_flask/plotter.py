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

class Plotter(tklib.Frame):
    def __init__(self, parent, debug=False, *args, **kwargs):
        super().__init__(*args, **kwargs)     # tklib.Frame place this with App.stack
        #super().__init__(parent, *args, **kwargs)


        self.lastmouse = None

        self.debug = debug
        self.c = None
        self.reference_id = None
        self.nav = None
        self.ch = 0
        self.cw = 0

        self.platten = (0,0, 426, 403)  # mm
        self.head = (-25,-35, 25, 25)  # mm
        self.carrige = (-51, -88, 493, -45)  # mm
        self.frame   = (-53, -90, 495, 430)  # mm
        self.led   = (-17, -1)  # mm

        self.reference = self.frame
        self.reference = Plotter.box_grow(self.frame, 10)

        pixel_per_mm = 1
        self.zoom = pixel_per_mm
        self.__delta = 1.3  # zoom magnitude

        bx1, by1, bx2, by2 = self.reference
        w = (bx2-bx1) * pixel_per_mm
        h = (by2-by1) * pixel_per_mm

        self.xy_readout = tk.StringVar()
        # put widgets in self. We are the new frame
        self.create_widgets(self, width=w, height=h)
        self.create_nav(self.nav)


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
        self.__min_side = self.min_side(self.c.coords(self.reference_id))

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

        #self.c.bind("<MouseWheel>", self.mouse_wheel)
        #self.c.bind("<Button-3>", self.pan)

        self.c.bind('<ButtonPress-3>', lambda event: self.c.scan_mark(event.x, event.y))
        #self.c.bind("<B3-Motion>", lambda event: self.c.scan_dragto(event.x, event.y, gain=1))
        self.c.bind("<B3-Motion>", self.on_b3_motion)
        self.c.bind('<Enter>', self.on_canvas_enter)

        self.c.bind('<Motion>', self.on_motion)


        # from junkyard
        self.canvas.bind('<MouseWheel>', self.__wheel)  # zoom for Windows and MacOS, but not Linux
        self.canvas.bind('<Button-5>',   self.__wheel)  # zoom for Linux, wheel scroll down
        self.canvas.bind('<Button-4>',   self.__wheel)  # zoom for Linux, wheel scroll up


        self.bind('<Enter>', self.on_canvas_home)
        self.update_idletasks()
        self.lastime = time.time()


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
        

    def on_b3_motion(self, e):
        self.c.scan_dragto(e.x, e.y, 1)
        self.update_readout(e)
        self.lastmouse = e

    def on_motion(self, e):
        self.update_readout(e)
        self.lastmouse = e

    def update_readout(self, e):
        if e == None: return
        x,y = e.x, e.y
        wx, wy = self.pixel_to_world((x, y))
        #print(f'mouse world {wx:5.1f} {wy:5.1f}')
        #self.xy_readout.set(f'X: {wx:5.1f}  Y: {wy:5.1f}')
        self.xy_readout.set(f'pix: {x:4d} {y:4d}  X: {wx:5.1f}  Y: {wy:5.1f}')
        cx, cy = self.c.canvasx(0), self.c.canvasy(0)
        self.xy_readout.set(f'can: {cx:4.0f} {cy:4.0f}   pix: {x:4d} {y:4d}  X: {wx:5.1f}  Y: {wy:5.1f}')

    def min_side(self, bbox):
        """ smaller side of a bounding box """
        return min(bbox[2]-bbox[0], bbox[3]-bbox[1])

    def on_canvas_home(self, e):
        bbox = self.c.bbox('all')    # canvas units, everything on the canvas
        print(f'--- home key pressed: bbox = {bbox}')

        # update scroll bar length and position
        # the canvas knows what its drawing view is
        #self.c.configure(scrollregion = bbox)

    def on_canvas_enter(self, e):
        bbox = self.c.bbox('all')    # canvas units, everything on the canvas
        print(f'--- bbox = {bbox}')

    def create_widgets(self, parent, width=400, height=300):
        
        f = parent
        f.pack_configure(fill='both', expand=True, padx=0, pady=0)  

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
        
        c = tk.Canvas(f, bg='powder blue', width=width, height=height)
        c.grid(row=1, column=0, sticky='nswe')
        self.c = c
        self.canvas = c

        sy = ttk.Scrollbar(f, orient=tk.VERTICAL)
        sy.grid(row=1, column=1, sticky='nse')
        self.sy = sy

        sx = ttk.Scrollbar(f, orient=tk.HORIZONTAL)
        sx.grid(row=2, column=0, sticky='swe')
        self.sx = sx

        #c.configure(scrollregion=point_scale(self.frame, self.zoom))

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
        #c.configure(scrollregion=point_scale(self.frame, self.zoom))
        c.configure(scrollregion=point_scale(self.reference, self.zoom))
        c.update()
        # set the callback function for the scrollbar to the xview, yview methods in the canvas
        sx.configure(command = c.xview)
        sy.configure(command = c.yview)



    def create_nav(self, f):
        home = tklib.Button(text="zoom reset", cmd=self.reset_zoom)
        home.pack_configure(side='left')

        test = tklib.Button(text="add test R", cmd=self.test_add_platten)
        test.pack_configure(side='left')

        tklib.Button(text="update conv", cmd=self._update_converters
           ).pack_configure(side='left')


        status = tklib.Label(text="status")
        status.pack_configure(side='left')

        xy = tklib.Label(text="0,0", textvariable=self.xy_readout)
        xy.pack_configure(side='right')
        

    def scaled_tuple(self, xy, scale):
        if len(xy) == 4:
           return (xy[0]*scale, xy[1]*scale, xy[2]*scale, xy[3]*scale)
        if len(xy) == 2:
           return (xy[0]*scale, xy[1]*scale)
        

    def scrollreg(self):
        pass

    def hud_init(self):
        hudtext = 'hello'
        self.hud = tk.Label(text=hudtext)
        
    def hud_update(self):
        pass


    @staticmethod
    def scale_to_fit(box, target):
        xscale = (target[2] - target[0]) / (box[2] - box[0])
        yscale = (target[3] - target[1]) / (box[3] - box[1])
        return min(xscale, yscale)

    def reset_zoom(self, event=None):
        """ set zoom to fit reference to window
            drag reference UL to window UL
        """
        #self.c.xview(0, 1)
        #self.c.yview(0, 1)

        #ref_can = self.c.coords(self.reference_id)
        #self.c.configure(scrollregion=ref_can)

        #self.c.configure(scrollregion=point_scale(self.reference, self.zoom))


        ref_can = self.c.coords(self.reference_id)

        x1 = ref_can[0]
        y1 = ref_can[1]
        x2 = self.c.canvasx(0)
        y2 = self.c.canvasy(0)

        dx = x2 - x1
        dy = y2 - y1

        self.c.move('all', dx, dy)
        #self.update()


        scale = self.scale_to_fit(ref_can, (0, 0, self.cw, self.ch))
        scale = round(scale, 3)
        self.zoom *= scale

        self.c.scale('all', x2, y2, scale, scale)
        #self.update()
        self._update_converters()
        self.__show_image()

        return

        x, y = ref_can[0] - self.c.canvasx(0), ref_can[1] - self.c.canvasy(0)
        x2, y2 = 50, 50

        print(f'reset_zoom  ref_can {Plotter.box_str(ref_can)}')
        print(f'reset_zoom  scale={scale}  mark={x,y}  dragto={x2,y2}')

        self.c.scan_mark(int(x), int(y))
        self.c.scan_dragto(int(x2), int(y2), 1)

        print(f'reset_zoom  ref_can {Plotter.box_str(ref_can)}')
        print(f'reset_zoom  UL  {self.c.canvasx(0), self.c.canvasy(0)}')

        return

        self.update()


        ref_can = self.c.coords(self.reference_id)
        self.c.scale('all', ref_can[0], ref_can[1], scale, scale)
        self.update()
        #self._update_converters()

        # (ref_can[0], ref_can[1]) should be the same since its the scaling origin
        #ref_can = self.c.coords(self.reference_id)  # get image area in pixels


        print(f'reset_zoom  scale={scale}  mark={x,y}')

        self._update_converters()
        self.__show_image()

        #bbox = self.c.bbox('all')    # canvas units, everything on the canvas
        #self.c.configure(scrollregion = bbox)

        print(f'zoom reset:   machine frame:{Plotter.box_str(self.frame)}')

    @staticmethod
    def box_grow(b, d):
        return (b[0]-d, b[1]-d, b[2]+d, b[3]+d)

    @staticmethod
    def box_str(b):
        return f'{b[0]:7.1f} {b[1]:7.1f}  {b[2]:7.1f} {b[3]:7.1f}'

    def tag_cb(self, e):
        print(f'canvas tag_cb: {e}')

    def configure(self, e):
        print(f'canvas configure: {e}')
        self.ch = e.height
        self.cw = e.width
        self._update_converters()

        #tklib.whatami(self.c, self.sy)

    def xview(self, e):
        print(f'xview: {e} {sx}')
        pass

    def yview(self, e):
        print(f'yview: {e} {sy}')
        pass

    def pan(self, e):
        print(f'pan: {e}')
        print(self.sx.get(), self.sy.get())

        s1, s2 = self.sx.get()
        w = s2 - s1
        s1 = e.x/self.cw - w / 2
        s2 = e.x/self.cw + w / 2
        self.sx.set(s1, s2)
        #self.sy.set(e.y/self.ch)


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

        #print(f'image_pix {type(image_pix)} {type(image_pix[0])} {image_pix} pixels')

        # get reference area in window pixel units
        can_offset = (self.c.canvasx(0), self.c.canvasy(0))
        ref_pix = (ref_can[0] - can_offset[0],
                   ref_can[1] - can_offset[1],
                   ref_can[2] - can_offset[0],
                   ref_can[3] - can_offset[1])

        cpw = []
        self.fpw = self.map_func(ref_pix, self.reference, cpw, name='cpw')
        self.fwp = self.map_func(self.reference, ref_pix)

        # get visible area of the canvas in canvas pix units
        win_can = self.box_vis_canvas()
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

    def box_vis_canvas(self):
        """ canvas units at the visible area UL and LR """
        bc = (self.c.canvasx(0),  # get visible area of the canvas
              self.c.canvasy(0),
              self.c.canvasx(self.c.winfo_width()),
              self.c.canvasy(self.c.winfo_height()))
        return bc

    def __show_image(self):
        """ Show image on the Canvas. Implements correct image zoom almost like in Google Maps """
        box_image = self.c.coords(self.reference_id)  # get image area, pixel units
        box_canvas = self.box_vis_canvas() # get visible area of the canvas
        box_img_int = tuple(map(int, box_image))  # convert to integer or it will not work properly
        # Get scroll region box
        box_scroll = [min(box_img_int[0], box_canvas[0]), min(box_img_int[1], box_canvas[1]),
                      max(box_img_int[2], box_canvas[2]), max(box_img_int[3], box_canvas[3])]
        # Horizontal part of the image is in the visible area
        if  box_scroll[0] == box_canvas[0] and box_scroll[2] == box_canvas[2]:
            box_scroll[0]  = box_img_int[0]
            box_scroll[2]  = box_img_int[2]
        # Vertical part of the image is in the visible area
        if  box_scroll[1] == box_canvas[1] and box_scroll[3] == box_canvas[3]:
            box_scroll[1]  = box_img_int[1]
            box_scroll[3]  = box_img_int[3]
        # Convert scroll region to tuple and to integer
        self.c.configure(scrollregion=tuple(map(int, box_scroll)))  # set scroll region
        x1 = max(box_canvas[0] - box_image[0], 0)  # get coordinates (x1,y1,x2,y2) of the image tile
        y1 = max(box_canvas[1] - box_image[1], 0)
        x2 = min(box_canvas[2], box_image[2]) - box_image[0]
        y2 = min(box_canvas[3], box_image[3]) - box_image[1]
        if int(x2 - x1) > 0 and int(y2 - y1) > 0:  # show image if it in the visible area
            pass

        #print(f' image  zoom = {self.zoom}')
        #print(f' image   box = {box_image}')
        #print(f' canvas  box = {box_canvas}')
        #print(f' machine frame:{self.frame}')
        # in our case .. nothing to do all drawings

    def outside(self, x, y):
        """ Checks if the point (x,y) is outside the image area """
        bbox = self.canvas.coords(self.reference_id)  # get image area
        if bbox[0] < x < bbox[2] and bbox[1] < y < bbox[3]:
            return False  # point (x,y) is inside the image area
        else:
            return True  # point (x,y) is outside the image area


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
            if i < self.zoom: return  # 1 pixel is bigger than the visible area
            self.zoom *= self.__delta
            scale        *= self.__delta
        self.canvas.scale('all', x, y, scale, scale)  # rescale all objects
        self._update_converters()
        # Redraw some figures before showing image on the screen
        #self.redraw_figures()  # method for child classes
        self.__show_image()



def plotter_test():
    app = tklib.App('plotter test')

    Plotter(tklib.App.stack[-1])

    app.run()

if __name__ == '__main__':

    tklib.App.debug = True
    plotter_test()
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

