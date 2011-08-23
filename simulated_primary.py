#!/usr/bin/env python
#
# Copyright 2005, 2006 Free Software Foundation, Inc.
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


#
# This script acts as a simulated primary for qpCSMA/CA testing.
#


from gnuradio import gr, blks2
from gnuradio import eng_notation
from gnuradio.eng_option import eng_option
from optparse import OptionParser
from gnuradio import uhd

import time, struct, sys, random

# from current dir
from transmit_path import transmit_path
from pick_bitrate import pick_tx_bitrate
#import fusb_options

class my_top_block(gr.top_block):
    def __init__(self, options):
        gr.top_block.__init__(self)

        self._tx_freq            = options.tx_freq         # tranmitter's center frequency
        self._rate               = options.rate*options.num_channels           # USRP sample rate
        self.gain                 = options.gain               # USRP gain

        if self._tx_freq is None:
            sys.stderr.write("-f FREQ or --freq FREQ or --tx-freq FREQ must be specified\n")
            raise SystemExit

        # Set up USRP sink; also adjusts interp, and bitrate
        self._setup_usrp_sink()

        # copy the final answers back into options for use by modulator
        #options.bitrate = self._bitrate

        self.txpath = transmit_path(options)

        self.connect(self.txpath, self.u)
        #self.connect(self.txpath, gr.file_sink(gr.sizeof_gr_complex, "txpath.dat"))
        
        if options.verbose:
            self._print_verbage()
        
    def _setup_usrp_sink(self):
        """
        Creates a USRP sink, determines the settings for best bitrate,
        and attaches to the transmitter's subdevice.
        """
        self.u = uhd.usrp_sink(
            device_addr = "",
            io_type=uhd.io_type.COMPLEX_FLOAT32,
            num_channels=1,
        )

        self.u.set_samp_rate(self._rate)

        # Set center frequency of USRP
        ok = self.set_freq(self._tx_freq)

        # Set the USRP for maximum transmit gain
        # (Note that on the RFX cards this is a nop
        gain = self.u.get_gain_range()
        #set the gain to the midpoint if it's currently out of bounds
        if self.gain > gain.stop() or self.gain < gain.start():
            self.gain = (gain.stop() + gain.start()) / 2
        self.set_gain(self.gain)

    def set_freq(self, target_freq):
        """
        Set the center frequency we're interested in.

        @param target_freq: frequency in Hz
        @rypte: bool

        Tuning is a two step process.  First we ask the front-end to
        tune as close to the desired frequency as it can.  Then we use
        the result of that operation and our target_frequency to
        determine the value for the digital up converter.
        """
        r = self.u.set_center_freq(target_freq)
        
    def set_gain(self, gain):
        """
        Sets the analog gain in the USRP
        """
        self.u.set_gain(gain)

    def add_options(normal, expert):
        """
        Adds usrp-specific options to the Options Parser
        """
        add_freq_option(normal)
        normal.add_option("-v", "--verbose", action="store_true", default=False)
        expert.add_option("", "--tx-freq", type="eng_float", default=None,
                          help="set transmit frequency to FREQ [default=%default]", metavar="FREQ")
        expert.add_option("-r", "--rate", type="eng_float", default=1e6,
                          help="set fpga sample rate to RATE [default=%default]")
    # Make a static method to call before instantiation
    add_options = staticmethod(add_options)

    def _print_verbage(self):
        """
        Prints information about the transmit path
        """
        #print "modulation:      %s"    % (self._modulator_class.__name__)
        print "sample rate      %3d"   % (self._rate)
        print "Tx Frequency:    %s"    % (eng_notation.num_to_str(self._tx_freq))
        print "Tx Gain:         %s"    % (self.gain)
        

def add_freq_option(parser):
    """
    Hackery that has the -f / --freq option set both tx_freq and rx_freq
    """
    def freq_callback(option, opt_str, value, parser):
        parser.values.rx_freq = value
        parser.values.tx_freq = value

    if not parser.has_option('--freq'):
        parser.add_option('-f', '--freq', type="eng_float",
                          action="callback", callback=freq_callback,
                          help="set Tx and/or Rx frequency to FREQ [default=%default]",
                          metavar="FREQ")

# /////////////////////////////////////////////////////////////////////////////
#                                   main
# /////////////////////////////////////////////////////////////////////////////

def main():

    def send_pkt(payload='', eof=False):
        return tb.txpath.send_pkt(payload, eof)

    parser = OptionParser(option_class=eng_option, conflict_handler="resolve")
    expert_grp = parser.add_option_group("Expert")
    parser.add_option("-s", "--size", type="eng_float", default=400,
                      help="set packet size [default=%default]")
    parser.add_option("-M", "--megabytes", type="eng_float", default=1.0,
                      help="set megabytes to transmit [default=%default]")
    parser.add_option("","--discontinuous", action="store_true", default=False,
                      help="enable discontinuous mode")
    parser.add_option("","--gain", type="eng_float", default=13,
                      help="set transmitter gain [default=%default]")
    parser.add_option("","--channel-interval", type="eng_float", default=.25,
                      help="set the time between channel changes [default=%default]")
    parser.add_option("","--num-channels", type="int", default=1,
                      help="set number of (contiguous) occupied channels [default=%default]")
    parser.add_option("", "--start-freq", type="eng_float", default="631M",
                          help="set the start of the frequency band to sense over [default=%default]")
    parser.add_option("", "--end-freq", type="eng_float", default="671M",
                          help="set the end of the frequency band to sense over [default=%default]")
                      
    my_top_block.add_options(parser, expert_grp)
    transmit_path.add_options(parser, expert_grp)
    blks2.ofdm_mod.add_options(parser, expert_grp)
    blks2.ofdm_demod.add_options(parser, expert_grp)
    #fusb_options.add_options(expert_grp)

    (options, args) = parser.parse_args ()

    total_samp_rate = options.num_channels*options.rate

    # build the graph
    tb = my_top_block(options)
    
    r = gr.enable_realtime_scheduling()
    if r != gr.RT_OK:
        print "Warning: failed to enable realtime scheduling"

    tb.start()                       # start flow graph
    
    # generate and send packets
    nbytes = int(1e6 * options.megabytes)
    n = 0
    pktno = 0
    pkt_size = int(options.size)

    #timing parameters
    last_change = time.clock()
    
    while n < nbytes:
        if time.clock() - last_change < options.channel_interval:
            #pktno % 65535 to account for sending very large amounts of data
            send_pkt(struct.pack('!H', pktno % 65535) + (pkt_size - 2) * chr(pktno & 0xff))
            n += pkt_size
            sys.stderr.write('.')
            if options.discontinuous and pktno % 5 == 1:
                time.sleep(1)
            pktno += 1
        else:
            
            #change channels
            if options.num_channels == 1:
                new_freq = options.start_freq + (random.uniform(0,6))*options.rate
            elif options.num_channels == 3:
                new_freq = options.start_freq + (random.uniform(1,5))*options.rate
            else:
                pass
                #just do nothing for now
            last_change = time.clock()
            print "\nchanging frequencies to ", new_freq
            tb.set_freq(new_freq)
        
    send_pkt(eof=True)
    tb.wait()                       # wait for it to finish

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
