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


class Plotter(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        f = self
        f.pack_configure(fill='both', expand=True)  

        # how f will manage its children
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        # scrolls get only what they need
        f.columnconfigure(1, weight=0)
        f.rowconfigure(1, weight=0)

        # stuff in f
        c = tk.Canvas(f, bg='powder blue', width=400, height=300)
        c.grid(row=0, column=0, sticky='nswe')

        sx = ttk.Scrollbar(f, orient=tk.HORIZONTAL, command=self.xview)
        sx.grid(row=1, column=0, sticky='swe')

        sy = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self.yview)
        sy.grid(row=0, column=1, sticky='nse')

        print(c)
        print(sx)
        print(sy)

        id = c.create_line(10,10, 100, 100, width=2, tags='1')


    def xview():
        pass
    def yview():
        pass



def plotter_test():
    app = tklib.App('plotter test')

    Plotter(tklib.App.stack[-1])

    app.run()

if __name__ == '__main__':

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

