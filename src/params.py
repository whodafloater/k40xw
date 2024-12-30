# 2014 whodafloater
# MIT license

# A class for managing an applications configurable parameters
#    file write
#    file read
#    bounds checking
#
#    parameters are defined by a dict
#        d[name] = [type, default, min, max, unit, sfmt, ffmt]
#
# scalar units:  mm, in, px, pct, u, rat, dpi
# velocity units:  mm/sec, in/min
# True strings have ffmt = ""
# Numeric fields have a float format string, ffmt != ""
# Numeric fields are strings so they can hold bad user input

from tkinter import *
from tkinter.filedialog import *
import re
import os

class Params:
    def __init__(self):

        self.title = "K40 Whisperer Settings"
        self.ident = "k40_whisperer_set"
        self.byline = "by Scorch - 2019, whodafloater 2024"
        self.version = "0.68"

        d = dict()
        self.d = d

        d['include_Reng']      = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]
        d['include_Rpth']      = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['include_Veng']      = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]
        d['include_Vcut']      = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]
        d['include_Gcde']      = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]
        d['include_Time']      = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]

        d['halftone']          = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]
        d['HomeUR']            = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['inputCSYS']         = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['advanced']          = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]

        d['mirror']            = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['rotate']            = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['negate']            = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['engraveUP']         = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['init_home']         = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]
        d['post_home']         = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['post_beep']         = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['post_disp']         = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['post_exec']         = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]

        d['pre_pr_crc']        = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]
        d['inside_first']      = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]

        d['comb_engrave']      = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['comb_vector']       = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['zoom2image']        = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['rotary']            = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['reduced_mem']       = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]
        d['input_dpi']         = [StringVar,    1000, 100, 1000, "dpi", ":s", "%.0f"]
        d['wait']              = [BooleanVar,   1, 0,    1, "", ":s", "%.0f"]

        d['trace_w_laser']     = [BooleanVar,   0, 0,    1, "", ":s", "%.0f"]

        d['trace_gap']         = [StringVar,   0, 0,     1, "mm",     ":s", "%.0f"]
        d['trace_speed']       = [StringVar,   50, 0,   100, "mm/sec", ":s", "%.0f"]


        d['Reng_feed']         = [StringVar,   100, 0,  600, "mm/sec", ":s", ":.0f"]
        d['Veng_feed']         = [StringVar,   20,  0,  600, "mm/sec", ":s", ":.0f"]
        d['Vcut_feed']         = [StringVar,   10,  0,  600, "mm/sec", ":s", ":.0f"]

        d['Reng_pow']          = [StringVar,   5, 0,    1, "pct", ":s", ":.0f"]
        d['Veng_pow']          = [StringVar,   5, 0,    1, "pct", ":s", ":.0f"]
        d['Vcut_pow']          = [StringVar,   5, 0,    1, "pct", ":s", ":.0f"]
        d['Reng_passes']       = [StringVar,   1, 0,    1, "u", ":s", ":.0f"]
        d['Veng_passes']       = [StringVar,   1, 0,    1, "u", ":s", ":.0f"]
        d['Vcut_passes']       = [StringVar,   1, 0,    1, "u", ":s", ":.0f"]
        d['Gcde_passes']       = [StringVar,   1, 0,    1, "u", ":s", ":.0f"]

        d['board_name']        = [StringVar,   "LASER-M2", 0, 1, "", ":s", ""]
        d['units']             = [StringVar,   "mm", 0,    1,    "", ":s", ""]

        d['jog_step']          = [StringVar,   10, 0.1,   100, "mm", ":s", ":.0f"]
        d['rast_step']         = [StringVar,   0.002, 0,  1,   "in", ":s", ":.0f"]
        d['ht_size']           = [StringVar,   500, 0,    1,   "px", ":s", ":.0f"]

        d['LaserXsize']        = [StringVar,   425, 0,    1000, "mm", ":s", ":.0f"]
        d['LaserYsize']        = [StringVar,   395, 0,    1000, "mm", ":s", ":.0f"]
        d['LaserXscale']       = [StringVar,   1.000, 0,  2,  "rat", ":s", ":.3f"]
        d['LaserYscale']       = [StringVar,   1.000, 0,  2,  "rat", ":s", ":.3f"]
        d['LaserRscale']       = [StringVar,   1.000, 0,  2,  "rat", ":s", ":.3f"]

        d['rapid_feed']        = [StringVar,   0.0, 1,   600, "mm/sec", ":s", ":.0f"]
        d['gotoX']             = [StringVar,   0.0, 0,  1000,     "mm", ":s", ":.3f"]
        d['gotoY']             = [StringVar,   0.0, 0,  1000,     "mm", ":s", ":.3f"]

        d['bezier_M1']         = [StringVar,   2.5, 0,    1, "", ":s", ":.3f"]
        d['bezier_M2']         = [StringVar,   0.50, 0,   1, "", ":s", ":.3f"]
        d['bezier_weight']     = [StringVar,   3.5, 0,    1, "", ":s", ":.3f"]

        d['n_egv_passes']      = [StringVar,   1, 0,      1, "u", ":s", ":.0f"]

        d['t_timeout']         = [StringVar,   200, 0,    1, "sec", ":s", ":.0f"]
        d['n_timeouts']        = [StringVar,   30, 0,     1, "u", ":s", ":.0f"]
        d['ink_timeout']       = [StringVar,   3, 0,      1, "sec", ":s", ":.0f"]

        d['gcode_import_spindle_power_scale'] = [StringVar, 1, 0, 1, "rat", ":s", ":.3f"]

        d['designfile']        = [StringVar,   "../test/Drawing1.DXF", 0, 1, "", ":s", ""]
        d['inkscape_path']     = [StringVar,   "", 0,    1, "", "%s", ""]
        d['batch_path']        = [StringVar,   "", 0,    1, "", "%s", ""]

        d['min_vector_speed']  = [StringVar,   1.1, 1.1,  100, "in/min", "%s", ":.0f"]  # in/min
        d['min_raster_speed']  = [StringVar,   12,  12,   100, "in/min", "%s", ":.0f"]  # in/min

    # Did not need this... idea was to create a parameter class that
    # K40 W would subclass 
    def superclass(self):
        code = ''
        code = code + f'class K40:\n'
        code = code + f'    def __init__(self):\n'
        d = self.d
        for n in d:
            name = n
            objtype = d[n][0]
            value =   d[n][1]
            minval =  d[n][2]
            maxval =  d[n][3]
            code = code + f'        self.{name:30s} = {objtype.__name__}()\n'
        return code


    def instantiate_params(self, context):
        """Instantiate all the parameters in a context

        After calling this function you can access all the values as
        you normally would. For example if you have a d['mySpecialVar']:

        value = mySpecialVar.get()
        mySpecialVar.set(value)
        """

        d = self.d
        for n in d:
            if len(d[n]) != 7:
               print(f'WARNING: parameter {n} is not fully defined in {__name__}')
            name = n
            objtype = d[n][0]
            value =   d[n][1]
            minval =  d[n][2]
            maxval =  d[n][3]

            #print(f'instantiate_params: {name} {value}')
            context.__dict__[name] = objtype()
            context.__dict__[name].set(value)


    def report(self, context):
        """Generate a parameter list suitable for printing or saving.
           Parameter values are retrieved from a specific context.
        """

        d = self.d

        header = []
        header.append(f'( {self.title}: {self.version} )')
        header.append(f'( {self.byline} )')
        header.append("(=========================================================)")

        for name in d:
            objtype = d[name][0]
            value = context.__dict__[name].get()
            unit = d[name][4]
            if unit == '': unit = '""'

            ffmt = d[name][6]

            if objtype == BooleanVar:
                value = int(value)

            elif ffmt == '%.0f':
                value = int(value)

            elif ffmt != '':
                ffmt = '{' + ffmt + '}'
                value = ffmt.format(float(value))

            if value == '':
                value = '""'
 
            s = f'({self.ident} {name:13s} {str(value)} {unit})'
            header.append(s)

        header.append("(=========================================================)")
        return header


    def read(self, filename, context):
        """Read parameters from a file and update cooresponding 
           object values in a context
        """
        try:
            fin = open(filename,'r')
        except:
            fmessage("Unable to open file: %s" %(filename))
            return

        for line in fin:
            if not self.ident in line: continue
            f = re.split(r'[() \t]+', line)

            while not self.ident in f.pop(0) and len(f):
               pass

            name = f.pop(0)
            value = f.pop(0)
            unit = f.pop(0)

            #print(f' name: {name:35s} | {value}')
            context.__dict__[name].set(value)

    def convert(self, value, old, new):
        if old == new: return 1

        s = 1
        dpi = self.d['input_dpi'][1]   # just the default

        if '/min' in old:
            s = s / 60
        if 'in' in old:
            s = s * 25.4
        if 'dpi' in old:
            s = s / 25.4
            value = 1 / value
        if 'px' in old:
            s = 25.4/dpi

        if 'in' in new:
            s = s / 25.4
        if '/min' in new:
            s = s * 60
        if 'dpi' in new:
            s = s * 25.4
            value = 1 / value
        if 'px' in new:
            s = dpi/25.4

        return value * s

    def speed_check(self, name, value):
        # min_vector_speed
        # min_raster_speed
        pass



class TestApp:
    def __init__(self, master):
        self.master = master
        self.version = '0.68'
        p = Params()
        self.p = p

        p.instantiate_params(self)

        self.statusMessage = StringVar()
        self.statusMessage.set("Welcome to K40 Whisperer")
        self.statusbar = Label(self.master,
                               textvariable=self.statusMessage,
                               bd=1, relief=SUNKEN , height=1
                              )
        self.statusbar.pack(anchor=SW, fill=X, side=BOTTOM)

    def try_it(self):
        u = self.units.get()
        print(f'   units = {u}');

    def report_params(self):
        h = self.p.report(self)
        #for line in h:
        #    print(line)
        return h

    def test_save_settings(self):
        self.general_file_save(".", self.report_params(), fileforce = 'sample_params.txt')

    def save_settings(self):
        self.general_file_save(".", self.report_params())

    def general_file_save(self, place, data, fileforce = None):

        if fileforce == None:
           init_dir = os.path.dirname(place)
           fileName, fileExtension = os.path.splitext(place)
           init_file = os.path.basename(fileName)

           filename = asksaveasfilename(defaultextension = '.txt',
                                        filetypes = [("Text File","*.txt")],
                                        initialdir = init_dir,
                                        initialfile = init_file)
        else:
            filename = fileforce

        if filename == '': return
        if filename == (): return

        try:
            fout = open(filename,'w')
        except:
            self.statusMessage.set("Unable to open file for writing: %s" %(filename))
            self.statusbar.configure( bg = 'red' )
            return

        for line in data:
            try:
                fout.write(line+'\n')
            except:
                fout.write('(skipping line)\n')
                debug_message(traceback.format_exc())
        fout.close
        self.statusMessage.set("File Saved: %s" %(filename))
        self.statusbar.configure( bg = 'white' )

if __name__ == "__main__":

    root = Tk()
    t = TestApp(root)

    t.units.set("in")
    t.report_params()
    t.test_save_settings()

    t2 = TestApp(root)
    print(f't    units = {t.units.get()}');
    print(f't2   units = {t2.units.get()}');

    t2.p.read("sample_params.txt", t2)
    t2.general_file_save(".", t2.report_params(), fileforce = 'sample_params2.txt')

    #c = t2.p.superclass()
    #print(c)

    t.try_it()

    print(f't    units = {t.units.get()}');
    print(f't2   units = {t2.units.get()}');

    assert(abs(t.p.convert(1.0, 'in', 'mm') - 25.4) < 1e-9)
    assert(abs(t.p.convert(25.4, 'mm', 'in') - 1.0) < 1e-9)
    assert(abs(t.p.convert(10, 'mm/sec', 'in/min') - 10*60/25.4) < 1e-9)
    assert(abs(t.p.convert(10, 'in/min', 'mm/sec') - 10*25.4/60) < 1e-9)
    assert(abs(t.p.convert(10, 'px', 'mm') - 10/int(t.input_dpi.get())*25.4) < 1e-9)
        

    #root.mainloop()
