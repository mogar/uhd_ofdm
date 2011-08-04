#!/usr/bin/env python
#
# Copyright 2005,2007 Free Software Foundation, Inc.
# 
# This file is part of GNU Radio
# 
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

from gnuradio import gr, gru, eng_notation, optfir, window
from gnuradio.eng_option import eng_option
#from usrpm import usrp_dbid
import sys, struct
import math



class tune(gr.feval_dd):
    """
    This class allows C++ code to callback into python.
    """
    def __init__(self, tb):
        gr.feval_dd.__init__(self)
        self.tb = tb

    def eval(self, ignore):
        """
        This method is called from gr.bin_statistics_f when it wants to change
        the center frequency.  This method tunes the front end to the new center
        frequency, and returns the new frequency as its result.
        """
        try:
            # We use this try block so that if something goes wrong from here 
            # down, at least we'll have a prayer of knowing what went wrong.
            # Without this, you get a very mysterious:
            #
            #   terminate called after throwing an instance of 'Swig::DirectorMethodException'
            #   Aborted
            #
            # message on stderr.  Not exactly helpful ;)

            new_freq = self.tb.set_next_freq()
            return new_freq

        except Exception, e:
            print "tune: Exception: ", e


class parse_msg(object):
    def __init__(self, msg):
        self.center_freq = msg.arg1()
        self.vlen = int(msg.arg2())
        assert(msg.length() == self.vlen * gr.sizeof_float)

        # FIXME consider using Numarray or NumPy vector
        t = msg.to_string()
        self.raw_data = t
        self.data = struct.unpack('%df' % (self.vlen,), t)


class sense_path(gr.hier_block2):

    def __init__(self, usrp_rate, tuner_callback, options):
        gr.hier_block2.__init__(self, "sense_path",
                gr.io_signature(1, 1, gr.sizeof_gr_complex), # Input signature
                gr.io_signature(0, 0, 0)) # Output signature
        
        self.usrp_rate = usrp_rate
        self.usrp_tune = tuner_callback
            
        self.threshold = options.threshold
        
        self.min_freq = options.start_freq
        self.max_freq = options.end_freq
        self.hold_freq = False
        
        self.num_channels = (self.max_freq - self.min_freq)/self.usrp_rate

        if self.min_freq > self.max_freq:
            self.min_freq, self.max_freq = self.max_freq, self.min_freq   # swap them
            
        self.fft_size = options.sense_fft_size


        if not options.real_time:
            realtime = False
        else:
            # Attempt to enable realtime scheduling
            r = gr.enable_realtime_scheduling()
            if r == gr.RT_OK:
                realtime = True
            else:
                realtime = False
                print "Note: failed to enable realtime scheduling"

        # build graph
        s2v = gr.stream_to_vector(gr.sizeof_gr_complex, self.fft_size)

        mywindow = window.blackmanharris(self.fft_size)
        fft = gr.fft_vcc(self.fft_size, True, mywindow)
        power = 0
        for tap in mywindow:
            power += tap*tap
            
        c2mag = gr.complex_to_mag_squared(self.fft_size)

        # FIXME the log10 primitive is dog slow
        log = gr.nlog10_ff(10, self.fft_size,
                           -20*math.log10(self.fft_size)-10*math.log10(power/self.fft_size))
        
        # Set the freq_step to 75% of the actual data throughput.
        # This allows us to discard the bins on both ends of the spectrum.

        #changed on 2011 May 31, MR -- maybe change back at some point
        self.freq_step = self.usrp_rate
        self.min_center_freq = self.min_freq + self.freq_step/2
        nsteps = math.ceil((self.max_freq - self.min_freq) / self.freq_step)
        self.max_center_freq = self.min_center_freq + (nsteps * self.freq_step)

        self.next_freq = self.min_center_freq
        
        tune_delay  = max(0, int(round(options.tune_delay * self.usrp_rate / self.fft_size)))  # in fft_frames
        dwell_delay = max(1, int(round(options.dwell_delay * self.usrp_rate / self.fft_size))) # in fft_frames

        self.msgq = gr.msg_queue(16)
        self._tune_callback = tune(self)        # hang on to this to keep it from being GC'd
        self.stats = gr.bin_statistics_f(self.fft_size, self.msgq,
                                    self._tune_callback, tune_delay, dwell_delay)

        # FIXME leave out the log10 until we speed it up
        #self.connect(self, s2v, fft, c2mag, log, stats)
        self.connect(self, s2v, fft, c2mag, self.stats)

        
    def set_next_freq(self):
        if self.hold_freq:
            return 0 #current_freq
            
        target_freq = self.next_freq
        self.next_freq = self.next_freq + self.freq_step
        if self.next_freq >= self.max_center_freq:
            self.next_freq = self.min_center_freq
            
        if not self.set_freq(target_freq):
            print "Failed to set frequency to", target_freq
                
        return target_freq
            
    def set_freq(self, target_freq):
        """
        Set the center frequency we're interested in.
            
        @param target_freq: frequency in Hz
        @rypte: bool
            
        Tuning is a two step process.  First we ask the front-end to
        tune as close to the desired frequency as it can.  Then we use
        the result of that operation and our target_frequency to
        determine the value for the digital down converter.
        """
        #updated 2011 May 31, MR
        #return self.u.tune(0, self.subdev, target_freq)
        return self.usrp_tune(target_freq)
    
    def set_hold_freq(self, hold):
        self.hold_freq = hold
        
    def update_samp_rate(self, samp_rate):
        self.usrp_rate = samp_rate
        self.freq_step = samp_rate
        
        
    def add_options(normal, expert):
        """
        Add sense-path specific options to the Options parser
        """
        normal.add_option("", "--tune-delay", type="eng_float", default=.01, metavar="SECS",
                          help="time to delay (in seconds) after changing frequency [default=%default]")
        normal.add_option("", "--dwell-delay", type="eng_float", default=.05, metavar="SECS",
                          help="time to dwell (in seconds) at a given frequncy [default=%default]")
        normal.add_option("-F", "--sense-fft-size", type="int", default=512,
                          help="specify number of FFT bins [default=%default]")
        normal.add_option("", "--threshold", type="eng_float", default=-54, 
                          help="set detection threshold [default=%default]")
        expert.add_option("", "--real-time", action="store_true", default=False,
                          help="Attempt to enable real-time scheduling")
        normal.add_option("", "--num-tests", type="intx", default=1,
                          help="set the number of times to test the frequency band [default=%default]")
        normal.add_option("", "--start-freq", type="eng_float", default="631M",
                          help="set the start of the frequency band to sense over [default=%default]")
        normal.add_option("", "--end-freq", type="eng_float", default="671M",
                          help="set the end of the frequency band to sense over [default=%default]")
    # Make a static method to call before instantiation
    add_options = staticmethod(add_options)
            

