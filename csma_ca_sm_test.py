#!/usr/bin/env python
#
# Copyright 2005,2006 Free Software Foundation, Inc.
# 
# This file is part of GNU Radio
# 
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
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


# /////////////////////////////////////////////////////////////////////////////
#
#    This code sets up up a virtual ethernet interface (typically gr0),
#    and relays packets between the interface and the GNU Radio PHY+MAC
#
#    What this means in plain language, is that if you've got a couple
#    of USRPs on different machines, and if you run this code on those
#    machines, you can talk between them using normal TCP/IP networking.
#
# /////////////////////////////////////////////////////////////////////////////


from gnuradio import gr, gru, blks2
#updated 2011 May 27, MR
from gnuradio import uhd
#from gnuradio import usrp
from gnuradio import eng_notation
from gnuradio.eng_option import eng_option
from optparse import OptionParser

import time
import struct
import sys
import os

# from current dir
from transmit_path import transmit_path
from receive_path import receive_path
#using state machine MAC, not while loop MAC (maybe this will work better?)
from csma_ca_mac_sm import *
    

# /////////////////////////////////////////////////////////////////////////////
#                             the flow graph
# /////////////////////////////////////////////////////////////////////////////

class usrp_graph(gr.top_block):
    def __init__(self, callback, options):
        gr.top_block.__init__(self)

        self._tx_freq            = options.tx_freq         # tranmitter's center frequency
        self._tx_gain            = options.tx_gain         # transmitter's gain
        self._samp_rate             = options.samp_rate       # sample rate for USRP
        self._rx_freq            = options.rx_freq         # receiver's center frequency
        self._rx_gain            = options.rx_gain         # receiver's gain

        if self._tx_freq is None:
            sys.stderr.write("-f FREQ or --freq FREQ or --tx-freq FREQ must be specified\n")
            raise SystemExit

        if self._rx_freq is None:
            sys.stderr.write("-f FREQ or --freq FREQ or --rx-freq FREQ must be specified\n")
            raise SystemExit

        # Set up USRP sink and source
        self._setup_usrp_sink()
        self._setup_usrp_source()

        # Set center frequency of USRP
        ok = self.set_freq(self._tx_freq)
        if not ok:
            print "Failed to set Tx frequency to %s" % (eng_notation.num_to_str(self._tx_freq),)
            raise ValueError

        self.txpath = transmit_path(options)
        self.rxpath = receive_path(callback, options)
        self.rx_valve = gr.copy(gr.sizeof_gr_complex)

        self.connect(self.txpath, self.u_snk)
        self.connect(self.u_src, self.rx_valve, self.rxpath)
        
        if options.verbose:
            self._print_verbage()

    def carrier_sensed(self):
        """
        Return True if the receive path thinks there's carrier
        """
        return self.rxpath.carrier_sensed()

    def _setup_usrp_sink(self):
        """
        Creates a USRP sink, determines the settings for best bitrate,
        and attaches to the transmitter's subdevice.
        """
        self.u_snk = uhd.usrp_sink(device_addr="", io_type=uhd.io_type.COMPLEX_FLOAT32, num_channels=1)
        self.u_snk.set_samp_rate(self._samp_rate) 
        
        self.u_snk.set_subdev_spec("", 0)

        g = self.u_snk.get_gain_range()
        #set the gain to the midpoint if it's currently out of bounds
        if self._tx_gain > g.stop() or self._tx_gain < g.start():
            self._tx_gain = (g.stop() + g.start()) / 2
        self.u_snk.set_gain(self._tx_gain)

    def _setup_usrp_source(self):
        self.u_src = uhd.usrp_source(device_addr="", io_type=uhd.io_type.COMPLEX_FLOAT32,
                                 num_channels=1)
        self.u_src.set_antenna("TX/RX", 0)
                                 
        self.u_src.set_subdev_spec("",0)
        self.u_src.set_samp_rate(self._samp_rate)
        
        g = self.u_src.get_gain_range()
        #set the gain to the midpoint if it's currently out of bounds
        if self._rx_gain > g.stop() or self._rx_gain < g.start():
            self._rx_gain = (g.stop() + g.start()) / 2
        self.u_src.set_gain(self._rx_gain)

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
        r_snk = self.u_snk.set_center_freq(target_freq, 0)
        r_src = self.u_src.set_center_freq(target_freq, 0)
        if r_snk and r_src:
            return True

        return False

    def add_options(normal, expert):
        """
        Adds usrp-specific options to the Options Parser
        """
        add_freq_option(normal)
        normal.add_option("-v", "--verbose", action="store_true", default=False)
        expert.add_option("", "--rx-freq", type="eng_float", default=None,
                          help="set Rx frequency to FREQ [default=%default]", metavar="FREQ")
        expert.add_option("", "--tx-freq", type="eng_float", default=None,
                          help="set Tx frequency to FREQ [default=%default]", metavar="FREQ")
        expert.add_option("-r", "--samp_rate", type="intx", default=800000,
                           help="set sample rate for USRP to SAMP_RATE [default=%default]")
        normal.add_option("", "--rx-gain", type="eng_float", default=17, metavar="GAIN",
                          help="set receiver gain in dB [default=%default].  See also --show-rx-gain-range")
        normal.add_option("", "--show-rx-gain-range", action="store_true", default=False, 
                          help="print min and max Rx gain available")        
        normal.add_option("", "--tx-gain", type="eng_float", default=11.5, metavar="GAIN",
                          help="set transmitter gain in dB [default=%default].  See also --show-tx-gain-range")
        normal.add_option("", "--show-tx-gain-range", action="store_true", default=False, 
                          help="print min and max Tx gain available")
        expert.add_option("", "--snr", type="eng_float", default=30,
                          help="set the SNR of the Rx channel in dB [default=%default]")
    # Make a static method to call before instantiation
    add_options = staticmethod(add_options)

    def _print_verbage(self):
        """
        Prints information about the transmit path
        """
        print
        print "PHY parameters"
        print "samp_rate        %3d"   % (self._samp_rate)
        print "Tx Frequency:    %s"    % (eng_notation.num_to_str(self._tx_freq))
        print "Tx antenna gain  %s"    % (self._tx_gain)
        print "Rx antenna gain  %s"    % (self._rx_gain)
        
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
pkts_rcvd = []
EOF_rcvd = False
num_acks = 0
def rx_callback(payload):
    global pkts_rcvd
    global EOF_rcvd
    global tx_failures
    global num_acks
    
    #print payload

    if payload == "R:EOF":
        EOF_rcvd = True
    if payload[:2] == "R:":
        pkts_rcvd.append(payload)
    elif payload == "T:ACK":
    	num_acks += 1
        


def main():
    global pkts_rcvd
    global EOF_rcvd
    global num_acks
    
    parser = OptionParser (option_class=eng_option, conflict_handler="resolve")
    expert_grp = parser.add_option_group("Expert")
    parser.add_option("-m", "--modulation", type="choice", choices=['bpsk', 'qpsk'],
                      default='bpsk',
                      help="Select modulation from: bpsk, qpsk [default=%%default]")
    parser.add_option("-v","--verbose", action="store_true", default=False)
    parser.add_option("-p","--packets", type="int", default = 40, 
                      help="set number of packets to send [default=%default]")
    parser.add_option("", "--address", type="string", default = 'a',
                      help="set the address of the node (addresses are a single char) [default=%default]")
    expert_grp.add_option("-c", "--carrier-threshold", type="eng_float", default=-20,
                      help="set carrier detect threshold (dB) [default=%default]")
    parser.add_option("", "--pkt-gen-time", type="eng_float", default=.5,
                      help="set the time between sending each packet (s) [default=%default]")
    parser.add_option("", "--pkt-padding", type="int", default=0,
                      help="pad packet with pkt-padding number of extra chars [default=%default]")
                      
    usrp_graph.add_options(parser, expert_grp)
    transmit_path.add_options(parser, expert_grp)
    receive_path.add_options(parser, expert_grp)
    blks2.ofdm_mod.add_options(parser, expert_grp)
    blks2.ofdm_demod.add_options(parser, expert_grp)
    cs_mac.add_options(parser, expert_grp)

    (options, args) = parser.parse_args ()
    if len(args) != 0:
        parser.print_help(sys.stderr)
        sys.exit(1)

    if options.rx_freq is None or options.tx_freq is None:
        sys.stderr.write("You must specify -f FREQ or --freq FREQ\n")
        parser.print_help(sys.stderr)
        sys.exit(1)

    # Attempt to enable realtime scheduling
    r = gr.enable_realtime_scheduling()
    if r == gr.RT_OK:
        realtime = True
    else:
        realtime = False
        print "Note: failed to enable realtime scheduling"

    pkts_sent = 0
    # instantiate the MAC
    mac = cs_mac(options, rx_callback)


    # build the graph (PHY)
    tx_failures = []
    tb = usrp_graph(mac.phy_rx_callback, options)

    mac.set_flow_graph(tb)    # give the MAC a handle for the PHY
    mac.set_error_array(tx_failures)
    
    print
    print "address:        %s"   % (options.address)
    print
    print "modulation:     %s"   % (options.modulation,)
    print "freq:           %s"   % (eng_notation.num_to_str(options.tx_freq))

    tb.rxpath.set_carrier_threshold(options.carrier_threshold)
    print "Carrier sense threshold:", options.carrier_threshold, "dB"

    tb.start()    # Start executing the flow graph (runs in separate threads)

    mac.start()
    
    while (pkts_sent < options.packets + 3):# or not EOF_rcvd):
        #if options.verbose:
        #    print "give a new packet to the MAC"
        if pkts_sent > options.packets:
            mac.new_packet('x', "EOF")
        else:
            mac.new_packet('x', str(pkts_sent).zfill(3) + options.pkt_padding * "k")    # run the tests
        pkts_sent += 1
    #while not EOF_rcvd:
        time.sleep(options.pkt_gen_time)
    
    #do stuff with the measurement results
    print
    print "this node sent:     ", pkts_sent, " packets"
    print "there were:         ", len(tx_failures), " packets that were not successfully sent"
    #print "this node received: ", num_acks, " ACK packets"
    print "this node rcvd:     ", len(set(pkts_rcvd)), " packets"
    print "there were:         ", len(pkts_rcvd) - len(set(pkts_rcvd)), " spurious packet retransmissions"
    print "collisions:         ", mac.collisions
    if options.pkt_padding != 0:
    	print "the packets this node sent were of length: ", len(str(pkts_sent).zfill(3) + options.pkt_padding * "k") + 2 # + 2 for the address chars
    #for item in pkts_rcvd:
    #    print "\t", item
    #print "succesfully sent the following packets"
    #for item in mac.sent_pkts:
    #    print "\t", item
    
    mac.stop()
    mac.wait()
    
    tb.stop()     # but if it does, tell flow graph to stop.
    tb.wait()     # wait for it to finish
    

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
