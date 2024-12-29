# k40xw

I wanted an simple GUI to do some human QA on gcode before it went to the X-Tool D1.

k40xw is leveraged from Scorch's original [K40 Whisperer](https://www.scorchworks.com/K40whisperer/k40whisperer.html)


# Why K40 Whisperer?

K40 Whisperer is plain old python and tkinter. The code base is small enough
to get your head around quickly.

It has is a laser cutter specific GUI that supports reading gcode, dxf, svg, and png.

Sometimes you appreciate the future better by dwelling in the past now and then.


So here's how it went:

* Start with [K40 Whisperer](https://www.scorchworks.com/K40whisperer/k40whisperer.html)
* Tease in some separation between
    * egv
    * ecoords
    * file  i/o
* make a machine base class for K40 Whisperer
    * make an xtool D1 driver class



# notes

The GUI use inch units. Y increases upward.

The gcode ripper is set to scale coordinates to inch when it reads. 

Same for the DXF reader.

The machine class expects inch data and scales it appropriatly before sending
to hardware.

Same for Y flipping, the machine class does the flip... and flip induced Y offset ... 


To understand K40, egv, LHYMICRO-GL, you have to check these out. Also good
learnings about python and API design in general:

* [K40Nano](https://github.com/K40Nano/K40Nano)
* [K40Tools](https://github.com/K40Nano/K40Tools)

# moving forward

More current alternatives:

* java, https://github.com/t-oster/VisiCut

* python, https://github.com/meerk40t/meerk40t


# Licesne

GPL-V3 per Scorch's orignal K40 Whisperer
