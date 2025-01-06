#!/usr/bin/env python3

import sys

#import inkex
#import simplestyle
#import simpletransform
#import cubicsuperpath
#import cspsubdiv
import traceback
#import struct

import math


from tkinter import *
from tkinter.filedialog import *
import tkinter.messagebox
import getopt

import params
from embedded_images import K40_Whisperer_Images

from PIL import Image


DEBUG = False

#import psyco
#psyco.full()
#LOAD_MSG = LOAD_MSG+"\nPsyco Loaded\n"

import pyclipper

from xtool_lib import xtool_CLASS
from xtool_lib import Xmsg
from machine_base import MachineBase

import time


def whatami(master, id):
    """
       What you get here is a list of options for Tk object
       https://tcl.tk/man/tcl8.6/TkCmd/contents.htm
       The first field is the instantiation parameter name.
       The second field is the database name, usually the same.
       Third field is the class name of the parameter.
    """
    if not DEBUG: return
    if not 'configure' in dir(id): return

    print(f'\n---whatami---\n{master.__class__} {master}    {id.__class__} {id}')
    print(id)

    c = id.configure()
    for a in c:
        print(f'   {a:20s} {c[a]}')

    # 
    #widget = Widget(master, "frame")
    #frame = Frame(master)
    #toplevel = Toplevel(master)
    #base = BaseWidget(master)

    dm = set(dir(id)) - set(dir(master))
    print('         directory')
    for a in dm:
        print(f'   {a:20s}')

    #dm = set(dir(frame)) - set(dir(toplevel))
    #print('         frame methods')
    #for a in dm:
    #    print(f'   {a:20s}')


class toplevel_dummy():
    def winfo_exists(self):
        return False

class ParamGui(Frame):
    def __init__(self, master=None, tunnel=None, *args, **kwargs):
        Frame.__init__(self, master, *args, **kwargs)
        # We subclassed Frame. We are the frame
        self.tunnel = tunnel
        self.setup(tunnel)

    def setup(self, tunnel):
        # we subclassed Frame. We are the frame
        w = self
        g=w

        #https://www.tcl.tk/man/tcl8.6/TkCmd/labelframe.htm
        #w.grid()
        fs = dict()
        lfargs = {'padx':3, 'pady':3, 'bg':'light blue'}
        fs['burger'] = LabelFrame(g, text='Burger',        **lfargs).grid(column=0, row=0)
        fs['bun']    = LabelFrame(g, text='Bun',           **lfargs).grid(column=1, row=0)
        fs['cheese'] = LabelFrame(g, text='Cheese Option', **lfargs).grid(column=0, row=1)
        fs['pickle'] = LabelFrame(g, text='Pickle Option', **lfargs).grid(column=1, row=1)

        for mtype, name, val in [
                ['burger', 'Beef',       'beef'],
                ['burger', 'Lamb',       'lamb'],
                ['burger', 'Vegetarian', 'beans'],
   
                ['bun'   , 'Plain',      'white'],
                ['bun'   , 'Sesame',     'seeds'],
                ['bun'   , 'Wholemeal',  'brown'],
            
                ['cheese', None,         'none'],
                ['cheese', 'Cheddar',    'cheddar'],
                ['cheese', 'Edam',       'edam'],
                ['cheese', 'Brie',       'brie'],
                ['cheese', 'Gruyere',    'gruyere'],
                ['cheese', 'Monterey Jack', 'jack'],
            
                ['pickle', None,         'none'],
                ['pickle', 'Gherkins',   'gherkins'],
                ['pickle', 'Onions',     'onion'],
                ['pickle', 'Chili',      'chili'],
               ]:

            print(f' {mtype:10s}  {str(name):15s}   {val:10s}')

            rb = Radiobutton(fs[mtype], text=name, variable=mtype, value=val, anchor='w').pack()

        #burger.set('beef')
        #bun.set('white')
        #cheese.set(None)
        #pickle.set(None)

class TrackPad(Frame):
    def __init__(self, master=None, tunnel=None, *args, **kwargs):
        Frame.__init__(self, master, *args, **kwargs)

        # We subclassed Frame. We are the frame
        self.configure(relief='sunken')
        self.pad = 0
        self.configure(padx=self.pad, pady=self.pad)
        self.configure(width=300, height=300, bg='light blue')

        self.setup(tunnel)

    def setup(self, tunnel):
        # we subclassed Frame. We are the frame
        w = self


        # something to force the size
        plattenC = Canvas(w, width=300, height=300, highlightthickness=0)
        platten = Canvas.create_rectangle(plattenC, 0, 0, 300-2*self.pad, 300-2*self.pad)
        plattenC.place(x=0, y=0)

        # Make a cursor tip using a circle on canvas
        tip_rad=5
        self.tip_rad = tip_rad
        tip1 = Canvas.create_oval(plattenC, 0, 0, tip_rad*2, tip_rad*2, width=0, fill="green", tags=("tip"))
        plattenC.moveto("tip", 150 - self.tip_rad, 150 - self.tip_rad)


        tipC = Canvas(w, width=tip_rad*2, height=tip_rad*2, highlightthickness=0, bg="light blue")
        #tipC.create_image(0, 0, anchor='nw', image=self.ball20_image)
        tip = Canvas.create_oval(tipC, 0, 0, tip_rad*2, tip_rad*2, width=0, fill="red" )
        #tip = Canvas.create_polygon(tipC, 0, 0,
        #                                  tip_rad*2, 0,
        #                                  tip_rad*2, tip_rad*2,
        #                                  0, tip_rad*2,
        #     width=0, fill="red")

        #tipC = Label(w, image=self.ball20_image)

        tipC.place_forget()

        self.x0, self.y0 = 150, 150
        self.lastx, self.lasty = 0,0
        self.mx, self.my = 0, 0
        self.lastmx, self.lastmy = 0, 0

        self.segid = []
        #dbg = Label(w, text='x,y=')
        #dbg.pack()

        self.px_to_mil = 12000 / 300
        self.mil_to_px = 1 / self.px_to_mil

        self.offsetx = 6000
        self.offsety = 6000

        self.machine_xi, self.machine_yi = tunnel.k40.head_position('mil')
        self.machine_x0, self.machine_y0 = tunnel.k40.head_position('mil')
        self.machine_x1, self.machine_y1 = tunnel.k40.head_position('mil')

        self.lasttime = time.time()

        def ballPanStart(event):
            # event x,y is the button local mouse position
            # captured here its the initial click position
            self.mx, self.my         = event.x, event.y
            self.lastmx, self.lastmy = event.x, event.y

            self.x0, self.y0 = event.x, event.y
            self.lastx = 0
            self.lasty = 0

            self.lasttime = time.time()
            self.segid = []

            print(f'start {event}')

            #cx=w.winfo_pointerx() - w.winfo_rootx() - tipC.winfo_width() / 2 - self.pad
            #cy=w.winfo_pointery() - w.winfo_rooty() - tipC.winfo_height() / 2 - self.pad
            #tipC.place(x=cx, y=cy)
            #w.update()

            #cx=w.winfo_pointerx() - w.winfo_rootx() - tipC.winfo_width() / 2 - self.pad
            #cy=w.winfo_pointery() - w.winfo_rooty() - tipC.winfo_height() / 2 - self.pad
            #tipC.place(x=cx, y=cy)

            plattenC.moveto("tip", self.mx - self.tip_rad, self.my - self.tip_rad)
            w.update()

            # machine commands
            # stepper enable, set relative coors
            tunnel.k40.q.put(Xmsg(1, ("manual_tracker_start", 0, 0)))


        def ballPan(event):
            tpw = w.winfo_width()
            tph = w.winfo_height()

            self.mx, self.my = event.x, event.y
            #print(f'Pan {self.mx, self.my}')

            #cx=w.winfo_pointerx() - w.winfo_rootx() - tipC.winfo_width() / 2 - self.pad
            #cy=w.winfo_pointery() - w.winfo_rooty() - tipC.winfo_height() / 2 - self.pad
            #tipC.place(x=cx, y=cy)

            plattenC.moveto("tip", self.mx - self.tip_rad, self.my - self.tip_rad)

            self.segid.append(
                 plattenC.create_line(self.lastmx, self.lastmy, self.mx, self.my, fill='pink')
                )
            self.lastmx, self.lastmy = self.mx, self.my


            x = (event.x - self.x0) * self.px_to_mil
            y = (event.y - self.y0) * self.px_to_mil

            distance = math.sqrt((self.lastx-x)*(self.lastx-x) + (self.lasty-y)*(self.lasty-y))
            if distance < 500: return

            delta_t = time.time()-self.lasttime
            if delta_t < 0.1: return

            qlen = tunnel.k40.q.qsize()
            if qlen > 2: return

            self.lasttime = time.time()

            speed = int(distance / 1000 * 25.4 / delta_t * 60)  # mm/min

            px0 = (self.lastx + self.offsetx) * self.mil_to_px
            py0 = (self.lasty + self.offsety) * self.mil_to_px
            px1 = (x + self.offsetx) * self.mil_to_px
            py1 = (y + self.offsety) * self.mil_to_px

            self.segid.append(
                 plattenC.create_line(px0, py0, px1, py1, fill='red')
                )
            
            # machine commands
            #  G0 to dx, dy
            command = ("manual_tracker", f'{x:.0f}', f'{-y:.0f}', speed)
            print(f'distance = {distance:.0f}mil delta_t = {delta_t:0.3f}sec  {command}')
            tunnel.k40.q.put(Xmsg(1, command))

            self.lastx = x
            self.lasty = y
            
            #tunnel.Rapid_Move(-JOG_STEP, 0, bound_check = False)
            #print(f'Pan {cx,cy}')

        def ballPanStop(event):

            #tipC.place_configure(x=x, y=y) # relative to the ojects parent UL
            #tipC.place_forget()

            # machine commands
            # disable stepper
            tunnel.k40.q.put(Xmsg(1, ("manual_tracker_stop", 0 , 0)))

            #print(f'stop {cx,cy}')

            # these are screen positions
            #print(f'stop root  { w.winfo_rootx(), w.winfo_rootx()}')
            #print(f'stop CC    {CC.winfo_rootx(),CC.winfo_rootx()}')
            #print(f'stop mouse {CC.winfo_pointerx(),CC.winfo_pointery()}')
            pass

        plattenC.bind("<1>"              , ballPanStart)
        plattenC.bind("<B1-Motion>"      , ballPan)
        plattenC.bind("<ButtonRelease-1>", ballPanStop)

        def configure(event):
            print(f".. Track Pad configure event")

        def tick():
            w.after(100, tick)
            self.machine_x0, self.machine_y0 = self.machine_x1, self.machine_y1
            self.machine_x1, self.machine_y1 = tunnel.k40.head_position('mil')

            x0 = (self.machine_x0 + self.offsetx ) * self.mil_to_px
            y0 = (-self.machine_y0 + self.offsety ) * self.mil_to_px
            x1 = (self.machine_x1 + self.offsetx ) * self.mil_to_px
            y1 = (-self.machine_y1 + self.offsety ) * self.mil_to_px

            xm1 = x1 / 1000 + 25.4
            ym1 = y1 / 1000 + 25.4

            if x0 != x1 or y0 != y1:
               print(f" ... tick  machine {time.time()-self.lasttime:0.3f} {self.machine_x1:5.0f}, {self.machine_y1:5.0f}   {x1:3.1f},{y1:3.1f}  {x1:3.0f},{y1:3.0f}")

            self.segid.append(
                 plattenC.create_line(
                     x0, y0,
                     x1, y1,
                     fill='blue')
                )

        tick()
        w.bind("<Configure>", configure)

        return


class JogPanel(Frame):
    def __init__(self, master=None, tunnel=None, nbuts=4, *args, **kwargs):
        Frame.__init__(self, master, *args, **kwargs)

        self.nbuts = nbuts

        # We subclassed Frame. We are the frame
        self.configure(relief='sunken')
        self.configure(padx=10, pady=10)

        self.load_images()
        self.setup(tunnel)

    def load_images(self):
        self.left_image  = PhotoImage(data=K40_Whisperer_Images.left_B64,  format='gif')
        self.right_image = PhotoImage(data=K40_Whisperer_Images.right_B64, format='gif')
        self.up_image    = PhotoImage(data=K40_Whisperer_Images.up_B64,    format='gif')
        self.down_image  = PhotoImage(data=K40_Whisperer_Images.down_B64,  format='gif')

        if self.nbuts > 4:
            self.UL_image  = PhotoImage(data=K40_Whisperer_Images.UL_B64, format='gif')
            self.UR_image  = PhotoImage(data=K40_Whisperer_Images.UR_B64, format='gif')
            self.LR_image  = PhotoImage(data=K40_Whisperer_Images.LR_B64, format='gif')
            self.LL_image  = PhotoImage(data=K40_Whisperer_Images.LL_B64, format='gif')
            self.CC_image  = PhotoImage(data=K40_Whisperer_Images.CC_B64, format='gif')


    def setup(self, tunnel):
        # we subclassed Frame. We are the frame
        w = self

        JOG_STEP = tunnel.value('jog_step', tunnel.units.get())

        def Move_Right(dummy=None):
            tunnel.Rapid_Move(JOG_STEP, 0, bound_check=False)

        def Move_Left(dummy=None):
            tunnel.Rapid_Move(-JOG_STEP, 0, bound_check = False)

        def Move_Up(dummy=None):
            tunnel.Rapid_Move(0, JOG_STEP, bound_check = False)

        def Move_Down(dummy=None):
            tunnel.Rapid_Move(0, -JOG_STEP, bound_check = False)

        def Move_g(*args):
            print(f'Move_g  {args}')
            pass

        # pad is space between the buttons,
        # ipad is internal space that make the button bigger
        pad = 2
        ip =  15
        bargs = {'padx':pad, 'pady':pad, 'ipadx':ip, 'ipady':ip}

        cf = Frame(w, padx=6, pady=6)
        Button(cf, image=self.right_image, command=Move_Right).grid(row=2, column=3, **bargs)
        Button(cf, image=self.left_image,  command=Move_Left ).grid(row=2, column=1, **bargs)
        Button(cf, image=self.up_image,    command=Move_Up   ).grid(row=1, column=2, **bargs)
        Button(cf, image=self.down_image,  command=Move_Down ).grid(row=3, column=2, **bargs)

        if self.nbuts > 4:
            Button(cf, image=self.UL_image, command=Move_g).grid(row=1, column=1, **bargs)
            Button(cf, image=self.UR_image, command=Move_g).grid(row=1, column=3, **bargs)
            Button(cf, image=self.LR_image, command=Move_g).grid(row=3, column=3, **bargs)
            Button(cf, image=self.LL_image, command=Move_g).grid(row=3, column=1, **bargs)
            Button(cf, image=self.CC_image, command=Move_g).grid(row=2, column=2, **bargs)

        cf.pack(side='right')
        return

class App(Frame):
    def __init__(self, master=None, opts=None, args=None):
        if master == None:
            master = Tk()
            #master.geometry("600x400")
      

        self.news = StringVar()

        #self.trace_window = toplevel_dummy()
        Frame.__init__(self, master)
        self.w = 780
        self.h = 490
        frame = Frame(master, width= self.w, height=self.h)
        self.master = master
        self.x = -1
        self.y = -1
        self.micro = False

        self.createImages()
        self.createWidgets(master)

        self.statusbar = self.sb2L        # status label used by K40 app

        self.tcount = 0
        self.tick()

        self.p = params.Params()
        au = AppUtils(self.p, self)
        # initialize parameters in the au context
        self.p.debug = DEBUG
        self.p.instantiate_params(au)
        self.p.sync_units(au)

        au.Initialize_Laser()
        self.tunnel = au
        #self.paramgui.tunnel = au

    def run(self):
        self.master.mainloop()

    def tick(self):
        self.after(1000, self.tick)
        self.tcount = self.tcount + 1
        if self.tcount == 3:
            self.manual_home_popup(self.tunnel)
            pass

        self.status.configure(text=f'tick: {self.tcount:5d}  {self.news.get()}')


    def value(self, name, unit):
        '''Helper to retrieve values in a specific base
           Note that the Param class instance needs to
           know which context to retrieve from
        '''
        return self.p.value(self, name, unit)


    def createImages(self):
        self.left_image  = PhotoImage(data=K40_Whisperer_Images.left_B64,  format='gif')
        self.right_image = PhotoImage(data=K40_Whisperer_Images.right_B64, format='gif')
        self.up_image    = PhotoImage(data=K40_Whisperer_Images.up_B64,    format='gif')
        self.down_image  = PhotoImage(data=K40_Whisperer_Images.down_B64,  format='gif')

        self.UL_image  = PhotoImage(data=K40_Whisperer_Images.UL_B64, format='gif')
        self.UR_image  = PhotoImage(data=K40_Whisperer_Images.UR_B64, format='gif')
        self.LR_image  = PhotoImage(data=K40_Whisperer_Images.LR_B64, format='gif')
        self.LL_image  = PhotoImage(data=K40_Whisperer_Images.LL_B64, format='gif')
        self.CC_image  = PhotoImage(data=K40_Whisperer_Images.CC_B64, format='gif')

        
        self.arrow_ne_image  = PhotoImage(file="image/arrow_ne.png")
        self.ball20_image  = PhotoImage(file="image/ball_20.png")

        #im = Image.open("image/ball_20.png")
        #print(f'ball image mode: {im.mode}')

    def createWidgets(self, m):
        s = self

        #tp = TrackPad(m)
        #s.tp = tp
        #tp.pack(fill='both', expand=True)
        #Label(tp, text='hello tp').pack()

        main = Frame()
        main.pack(fill='both', expand=True)
        Label(main, text='hello world').pack()

        #jp = JogPanel(m, self)
        #jp.pack(anchor='e')
        #s.jp = jp

        #pg = ParamGui(main)
        #pg.pack(anchor="w")
        #s.paramgui = pg


        sb = Frame(m, height=20, relief='sunken', bg='wheat', padx=2, pady=2)
        sb.pack(anchor='s', fill='x')

        sb2 = Frame(m, height=20, relief='sunken', bg='wheat', padx=2, pady=2)
        sb2.pack(anchor='s', fill='x')
        sv = StringVar()
        sb2L = Label(sb2, textvariable=sv, bd=1, relief='sunken' , height=1)
        sb2L.pack(anchor=SW, fill='both', side='bottom')

        s.sb = sb
        s.sb2 = sb
        s.sb2L = sb2L
        s.statusMessage = sv  # status var used status label

        #whatami(m, sb)

        st = Label(sb, text='hello tp')
        st.pack(anchor="w")
        s.status = st
        #whatami(m, st)




    def manual_home_popup(self, tunnel):
        # tunnel is the object where callbacks get funneled
        w = Toplevel(width=400, height=600)
        #w = Toplevel()
        w.grab_set()
        #w.resizable(0,0)
        w.title('Manual Home')
        return_value =  StringVar()
        return_value.set("none")

        def Close_Click():
            return_value.set("apply")
            w.destroy()

        def Cancel_Click():
            return_value.set("cancel")
            w.destroy()

        jp = JogPanel(w, tunnel)
        jp2 = JogPanel(w, tunnel, nbuts=9)
        tp = TrackPad(w, tunnel)

        data = [
          'The machine does not',
          'have an automatic Home',
          'function avalable',
          '',
          'Get up and do it yourself',
          '',
          'or use the buttons',
          '',
          'or do nothing',
         ]

        t = ''
        for line in data:
            t = t + line + '\n'
        lb = Label(w)
        lb.configure(text=t)

        bf = Frame(w)
        Button(bf, text=" Apply and Continue ", command = Close_Click).pack(side = RIGHT)
        Button(bf, text=" Cancel ", command = Cancel_Click).pack(side = RIGHT)

        bf.pack(side='bottom')
        tp.pack(side='right', fill="both", expand=True)
        jp.pack(side='right')
        lb.pack(side='left')

        print(tp.pack_info())
        root.wait_window(w)

        return return_value.get()


    def ball_tracker_experiment():
        # Make a cursor tip using a circle on canvas
        tip_rad=5
        self.tip_rad = tip_rad

        tipC = Canvas(w, width=tip_rad*2, height=tip_rad*2, highlightthickness=0)
        #tipC.create_image(0, 0, anchor='nw', image=self.ball20_image)
        tip = Canvas.create_oval(tipC,tip_rad/2,tip_rad/2,tip_rad/2*3,tip_rad/2*3, width=0, fill="red")

        #tipC = Label(w, image=self.ball20_image)

        tipC.place_forget()

        x0, y0 = 0,0
        dx, dy = 0,0
        def ballPanStart(event):
            # event x,y is the button local mouse position
            # captured here its the initial click position
            x0, y0 = event.x, event.y
            print(f'start {event}')

            #  CC.winfo_rootx is screen pos of UL of the button
            x0 = CC.winfo_rootx() - w.winfo_rootx()
            y0 = CC.winfo_rooty() - w.winfo_rooty()
            print(f'start CC rel loc {x0, y0}')

        def ballPan(event):
            #dx = event.x - x0
            #dy = event.y - y0
            #print(f'Pan {dx,dy}')o
            cx=w.winfo_pointerx() - w.winfo_rootx()
            cy=w.winfo_pointery() - w.winfo_rooty()

            tipC.place(x=cx-tip_rad, y=cy-tip_rad)
            print(f'Pan {cx,cy}')

        def ballPanStop(event):
            cx = CC.winfo_rootx() - w.winfo_rootx()
            cy = CC.winfo_rootx() - w.winfo_rooty()
            #tipC.place(x=cx, y=cy)
            #tipC.place(x=cx-tip_rad, y=cy-tip_rad)

            # absolute
            tipC.place(x=CC.winfo_rooty(), y=CC.winfo_rooty())

            x = CC.winfo_rootx() - w.winfo_rootx()
            x = x + CC.winfo_width() / 2 - tipC.winfo_width() / 2

            y = CC.winfo_rooty() - w.winfo_rooty()
            y = y + CC.winfo_height() / 2 - tipC.winfo_height() / 2

            #tipC.place_configure(x=x, y=y) # relative to the ojects parent UL
            tipC.place_forget()

            #print(f'stop {cx,cy}')

            # these are screen positions
            #print(f'stop root  { w.winfo_rootx(), w.winfo_rootx()}')
            #print(f'stop CC    {CC.winfo_rootx(),CC.winfo_rootx()}')
            #print(f'stop mouse {CC.winfo_pointerx(),CC.winfo_pointery()}')
            pass

        CC.bind("<1>"              , ballPanStart)
        CC.bind("<B1-Motion>"      , ballPan)
        CC.bind("<ButtonRelease-1>", ballPanStop)

        def configure(event):
            print(".. configure event")
            print(f'conf CC    {CC.winfo_rootx(),CC.winfo_rootx()}')
            tipC.place(x=CC.winfo_rooty(), y=CC.winfo_rooty())

        CC.bind("<Configure>", configure)

        self.CC = CC
        self.tipC = tipC
        self.mhp = w

        root.wait_window(w)

        self.CC = None
        self.tipC = None
        self.mhp = None
        return return_value.get()


class AppUtils:
    def __init__(self, params, gui, *args, **kwargs):

        self.p = params
        self.k40 = None

        # process command line args
        file_units = None
        #self.ipaddr = '192.168.0.106'

        self.statusMessage = gui.statusMessage
        self.statusMessage.set("Welcome")

        self.statusbar = gui.statusbar


    def value(self, name, unit):
        '''Helper to retrieve values in a specific base
           Note that the Param class instance needs to
           know which context to retrieve from
        '''
        return self.p.value(self, name, unit)


    def Initialize_Laser(self, event=None):
        #if self.GUI_Disabled:
        #    return
        #self.stop[0]=True
        #self.Release_USB()
        #self.k40=None
        #self.move_head_window_temporary([0.0,0.0])      

        #self.k40=K40_CLASS()
        #self.k40=MachineBase()
        self.k40 = xtool_CLASS()
        #self.simulate = True
        self.k40.IP = self.ipaddr.get()
        self.k40.PORT = self.ipport.get()
        self.k40.debug = DEBUG

        msg = 'ok'

        try:
            self.k40.initialize_device()
            msg = self.k40.say_hello()

        except Exception as e:
            error_text = "%s" %(e)

            if error_text == "Machine is Offline":
                self.k40=None
                self.statusMessage.set(f'INFO: {e}')
                self.statusbar.configure( bg = 'pink' )
                return

            if "BACKEND" in error_text.upper():
                error_text = error_text + " (libUSB driver not installed)"

            self.statusMessage.set("Connection Error: %s" %(error_text))
            self.statusbar.configure( bg = 'red' )
            self.k40=None
            debug_message(traceback.format_exc())
            return

        except:
            self.statusMessage.set("Unknown USB Error")
            self.statusbar.configure( bg = 'red' )
            self.k40 = None
            debug_message(traceback.format_exc())
            return

        self.k40.upload_safe_file()

        self.statusMessage.set(msg)
        self.statusbar.configure( bg = 'light green' )

        if self.k40 == None:
            return

        self.k40.upload_safe_file()

        return

    def Rapid_Move(self,dx,dy, bound_check=True):
        print(f'Rapid_Move  {dx} {dy}  bound_check:{bound_check}')

        dxmils = dx * 1000 / 25.4
        dymils = dy * 1000 / 25.4

        self.k40.q.put(Xmsg(9, ("rapid_move", int(dxmils), int(dymils))))


def debug_message(message):
    global DEBUG
    title = "Debug Message"
    if DEBUG:
        tkinter.messagebox.showinfo(title,message)

if __name__ == "__main__":

    #root = Tk()
    #root.geometry("600x400")
    #import tkinter.font
    #default_font = tkinter.font.nametofont("TkDefaultFont")
    #default_font.configure(size=9)
    #default_font.configure(family='arial')

    opts, args = None, None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hpd", ["help", "debug", "ip="])
    except:
        pass

    for option, value in opts:
        if option in ('-h','--help'):
            print('--ip         : machine IP address')
            print('--debug, -d  : turn on debug output')
            sys.exit()
        elif option in ('-d','--debug'):
            DEBUG=True

    App(None, opts, args).run()
