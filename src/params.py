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
# Application code can reference these as normal. For example "units",
#    self.units.get()
#    self.units.set("mm")
#
# These are tkinter.Variable classes. Bind a callack with:
#    self.units.trace_variable(mode, callback_fn)
#
# https://github.com/python/cpython/issues/66313
# https://github.com/python/cpython/blob/3.13/Lib/tkinter/__init__.py
#    use trace_add(mode, callback)
#       Mode is one of "read", "write", "unset", or a list or tuple of
#       such strings.
# 
#
# Scalar units:  mm, in, px, pct, u, rat, dpi
# Velocity units:  mm/sec, in/min
# True strings have ffmt = ""
# Numeric fields have a float format string, ffmt != ""
# Numeric fields are strings so they can hold bad user input
#
# The original K40w expects unit consistency:
#    units="mm" and  mm and mm/sec   or   units="in" and  in and in/mm
# Since these tkinter.Variable objects values are bound to
# the GUI widgets they must all be converted when the GUI "units"
# value is changed.
#
#
# ecoord data is always inch, mm/sec, pct power
# 
#
from tkinter import *
from tkinter.filedialog import *
import re
import os

class Params:
    def __init__(self):

        self.debug = False
        self.title = "K40 Whisperer Settings"
        self.ident = "k40_whisperer_set"
        self.byline = "by Scorch - 2019, whodafloater 2024"
        self.version = "0.68"

        self.numcheck = 1.23456789

        # mm precision   1 -> 10 mm     0.400 in
        #                0 ->  1 mm     0.040 in
        #               -1 ->  0.1 mm   0.004 in
        #               -2 ->  0.01 mm  0.0004 in
        f = dict()
        self.f = f
        f['mm'] = {1:'.0f', 0:'.0f', -1:'.1f', -2:'.2f', -9:'0.9f', 'd':'.0f'}
        f['in'] = {1:'.1f', 0:'.2f', -1:'.3f', -2:'.4f', -9:'.11f', 'd':'.0f'}
        f['mm/sec'] = {1:'.0f', 0:'.0f', -1:'.1f', -2:'.2f', 'd':'.0f'}
        f['in/min'] = {1:'.1f', 0:'.2f', -1:'.3f', -2:'.4f', 'd':'.0f'}
        f['rat'] = {1:'.0f', 0:'.0f', -1:'.1f', -2:'.2f', -3:'.3f', -4:'.4f'}
        f['pct'] = {1:'.0f', 0:'.0f', -1:'.1f', 'd':'.0f'}
        f['sec'] = {1:'.0f', 0:'.0f', -1:'.1f', -2:'.2f', -3:'.3f'}
        f['u'] =   {1:'.0f', 0:'.0f', -1:'.1f', -2:'.2f', -3:'.3f', 'd':'.0f'}
        f['dpi'] = {0:'.0f', 'd':'.0f'}
        f['px'] =  {0:'.0f', 'd':'.0f'}
        f['""'] =  {'""':'s', '':'s'}

        d = dict()
        self.d = d

        d['numcheck']          = [StringVar,    self.numcheck, 0, 1e9, "mm", ":s", -9]

        d['include_Reng']      = [BooleanVar,   1, 0,    1, "", ":s", ""]
        d['include_Rpth']      = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['include_Veng']      = [BooleanVar,   1, 0,    1, "", ":s", ""]
        d['include_Vcut']      = [BooleanVar,   1, 0,    1, "", ":s", ""]
        d['include_Gcde']      = [BooleanVar,   1, 0,    1, "", ":s", ""]
        d['include_Time']      = [BooleanVar,   1, 0,    1, "", ":s", ""]

        d['halftone']          = [BooleanVar,   1, 0,    1, "", ":s", ""]
        d['HomeUR']            = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['inputCSYS']         = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['advanced']          = [BooleanVar,   0, 0,    1, "", ":s", ""]

        d['mirror']            = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['rotate']            = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['negate']            = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['engraveUP']         = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['init_home']         = [BooleanVar,   1, 0,    1, "", ":s", ""]
        d['post_home']         = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['post_beep']         = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['post_disp']         = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['post_exec']         = [BooleanVar,   0, 0,    1, "", ":s", ""]

        d['pre_pr_crc']        = [BooleanVar,   1, 0,    1, "", ":s", ""]
        d['inside_first']      = [BooleanVar,   1, 0,    1, "", ":s", ""]

        d['comb_engrave']      = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['comb_vector']       = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['zoom2image']        = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['rotary']            = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['reduced_mem']       = [BooleanVar,   0, 0,    1, "", ":s", ""]
        d['input_dpi']         = [StringVar,    1000, 100, 1000, "dpi", ":s", "d"]
        d['wait']              = [BooleanVar,   1, 0,    1, "", ":s", ""]

        d['trace_w_laser']     = [BooleanVar,   0, 0,    1, "", ":s", ""]

        d['trace_gap']         = [StringVar,   0, 0,     1, "mm",      ":s", 0]
        d['trace_speed']       = [StringVar,   50, 0,   100, "mm/sec", ":s", 0]


        d['Reng_feed']         = [StringVar,   100, 0,  600, "mm/sec", ":s", 0]
        d['Veng_feed']         = [StringVar,   20,  0,  600, "mm/sec", ":s", 0]
        d['Vcut_feed']         = [StringVar,   10,  0,  600, "mm/sec", ":s", 0]

        d['Reng_pow']          = [StringVar,   5, 0,    1, "pct", ":s", "d"]
        d['Veng_pow']          = [StringVar,   5, 0,    1, "pct", ":s", "d"]
        d['Vcut_pow']          = [StringVar,   5, 0,    1, "pct", ":s", "d"]
        d['Reng_passes']       = [StringVar,   1, 0,    1, "u", ":s",   "d"]
        d['Veng_passes']       = [StringVar,   1, 0,    1, "u", ":s",   "d"]
        d['Vcut_passes']       = [StringVar,   1, 0,    1, "u", ":s",   "d"]
        d['Gcde_passes']       = [StringVar,   1, 0,    1, "u", ":s",   "d"]

        d['board_name']        = [StringVar,   "LASER-M2", 0, 1, "", ":s", ""]
        d['units']             = [StringVar,   "mm", 0,    1,    "", ":s", ""]

        d['jog_step']          = [StringVar,   10, 0.1,   100, "mm", ":s", -1]
        d['rast_step']         = [StringVar,   0.002, 0,  1,   "in", ":s", -2]
        d['ht_size']           = [StringVar,   500, 0,    1,   "px", ":s", "d"]

        d['LaserXsize']        = [StringVar,   425, 0,    1000, "mm", ":s", 0]
        d['LaserYsize']        = [StringVar,   395, 0,    1000, "mm", ":s", 0]
        d['LaserXscale']       = [StringVar,   1.000, 0,  2,  "rat", ":s", -3]
        d['LaserYscale']       = [StringVar,   1.000, 0,  2,  "rat", ":s", -3]
        d['LaserRscale']       = [StringVar,   1.000, 0,  2,  "rat", ":s", -3]

        d['linear_rapid_feed'] = [StringVar,   3000, 0, 3000, "in/min", ":s", 0]
        d['rapid_feed']        = [StringVar,   0.0, 0,   600, "mm/sec", ":s", 0]
        d['min_rapid_feed']    = [StringVar,   1.0, 1,     1, "in/min", ":s", 0]
        d['gotoX']             = [StringVar,   0.0, 0,  1000,     "mm", ":s", 0]
        d['gotoY']             = [StringVar,   0.0, 0,  1000,     "mm", ":s", 0]

        d['bezier_M1']         = [StringVar,   2.5, 0,    1, "u", ":s", -3]
        d['bezier_M2']         = [StringVar,   0.50, 0,   1, "u", ":s", -3]
        d['bezier_weight']     = [StringVar,   3.5, 0,    1, "u", ":s", -3]

        d['n_egv_passes']      = [StringVar,   1, 0,      1, "u", ":s", "d"]

        d['t_timeout']         = [StringVar,   200, 0,    1, "sec", ":s", 0]
        d['n_timeouts']        = [StringVar,   30, 0,     1, "u", ":s", "d"]
        d['ink_timeout']       = [StringVar,   3, 0,      1, "sec", ":s", 0]

        d['gcode_import_spindle_power_scale'] = [StringVar, 1, 0, 1, "rat", ":s", -2]

        d['designfile']        = [StringVar,   "../test/Drawing1.DXF", 0, 1, "", ":s", ""]
        d['inkscape_path']     = [StringVar,   "", 0,    1, "", "%s", ""]
        d['batch_path']        = [StringVar,   "", 0,    1, "", "%s", ""]

        d['min_vector_speed']  = [StringVar,   1.1, 1.1,  100, "in/min", "%s", 0]
        d['min_raster_speed']  = [StringVar,   12,  12,   100, "in/min", "%s", 0]

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

            if unit == '':
               unit = '""'

            ffmt = '{:' + self.f[unit][d[name][6]] + '}'
            #print(f'{name} {unit} {ffmt}')

            if objtype == BooleanVar:
                value = int(value)

            elif unit == '""':
                pass

            elif ffmt != '':
                value = ffmt.format(float(value))

            if value == '':
                value = '""'
 
            s = f'({self.ident} {name:13s} {str(value)} {unit} )'
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

        # K40 does more init based on the new value
        #   check for existance of designfile
        # default units to mm 
        #   set funits  (feed units, they just track mm, in)
        #   set units_scale
        #   trigger master_Configure()
        

    def convert(self, value, old, new):
        if old == new: return value

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

        #print(f'convert: {value} {old} to {new} --> {value*s}')
        return value * s

    def value(self, context, name, unit):
        '''Return a parameter value converted to a desired unit
           Note units are in this class instance
           values are in the application context
        '''
        data_val  = float(context.__dict__[name].get())
        data_unit = self.d[name][4]
        return self.convert(data_val, data_unit, unit)

    def speed_check(self, name, value):
        # min_vector_speed
        # min_raster_speed
        pass


    def fmtstr(self, name):
        d = self.d
        unit = d[name][4]
        if unit == '':
            unit = '""'
        #print(f'    format string for {name}  {self.f[unit][d[name][6]]}')
        return '{:' + self.f[unit][d[name][6]] + '}'

    def mm_to_in(self, context, name):
        u = self.d[name][4]
        if u == 'in': return
        if u != 'mm': raise Exception(f'expected "mm" units for parameter {name}')
        newvalue = float(context.__dict__[name].get()) / 25.4
        self.d[name][4] = 'in'
        newvalue = self.fmtstr(name).format(newvalue)
        context.__dict__[name].set(newvalue)
        if self.debug: print(f'unit change: {name} {context.__dict__[name].get()} {self.d[name][4]}')

    def in_to_mm(self, context, name):
        u = self.d[name][4]
        if u == 'mm': return
        if u != 'in': raise Exception(f'expected "in" units for parameter {name}')
        newvalue = float(context.__dict__[name].get()) * 25.4
        self.d[name][4] = 'mm'
        newvalue = self.fmtstr(name).format(newvalue)
        context.__dict__[name].set(newvalue)
        if self.debug: print(f'unit change: {name} {context.__dict__[name].get()} {self.d[name][4]}')

    def mmps_to_inpm(self, context, name):
        u = self.d[name][4]
        if u == 'in/min': return
        if u != 'mm/sec': raise Exception(f'expected "mm/sec" units for parameter {name}')
        newvalue = float(context.__dict__[name].get()) * 60 / 25.4
        self.d[name][4] = 'in/min'
        newvalue = self.fmtstr(name).format(newvalue)
        context.__dict__[name].set(newvalue)
        if self.debug: print(f'unit change: {name} {context.__dict__[name].get()} {self.d[name][4]}')

    def inpm_to_mmps(self, context, name):
        u = self.d[name][4]
        if u == 'mm/sec': return
        if u != 'in/min': raise Exception(f'expected "in/min" units for parameter {name}')
        newvalue = float(context.__dict__[name].get()) * 25.4 / 60
        self.d[name][4] = 'mm/sec'
        newvalue = self.fmtstr(name).format(newvalue)
        context.__dict__[name].set(newvalue)
        if self.debug: print(f'unit change: {name} {context.__dict__[name].get()} {self.d[name][4]}')

    def sync_units(self, context):
        units = context.__dict__['units'].get()
        d = self.d

        if units == 'mm':
            for name in d:
                u = self.d[name][4]
                if units in u:
                    continue
                if u == 'in':
                    self.in_to_mm(context, name)
                if u == 'in/min':
                    self.inpm_to_mmps(context, name)

        elif units == 'in':
            for name in d:
                u = self.d[name][4]
                if units in u:
                    continue
                if u == 'mm':
                    self.mm_to_in(context, name)
                if u == 'mm/sec':
                    self.mmps_to_inpm(context, name)

        else:
            raise Exception("no units?")


def assert_val(x, y):
    if __debug__:
       #print(f'    assertion: ({x}) == ({y}) ?')
       assert(abs(x - y) < 1e-6)
       #print(f'assertion passed: {x} {y}')


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

    fmt = '{:.0f}'
    value = 143/3
    value = fmt.format(value)
    print(f'value = {value}')

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
