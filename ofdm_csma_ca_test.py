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

import random
import time
import struct
import sys
import os

# from current dir
from transmit_path import transmit_path
from receive_path import receive_path
#import fusb_options

#print os.getpid()
#raw_input('Attach and press enter')


# /////////////////////////////////////////////////////////////////////////////
#
#   Use the Universal TUN/TAP device driver to move packets to/from kernel
#
#   See /usr/src/linux/Documentation/networking/tuntap.txt
#
# /////////////////////////////////////////////////////////////////////////////

#removed 2011 May 27, MR
# Linux specific...
# TUNSETIFF ifr flags from <linux/tun_if.h>

#IFF_TUN		= 0x0001   # tunnel IP packets
#IFF_TAP		= 0x0002   # tunnel ethernet frames
#IFF_NO_PI	= 0x1000   # don't pass extra packet info
#IFF_ONE_QUEUE	= 0x2000   # beats me ;)

#def open_tun_interface(tun_device_filename):
#    from fcntl import ioctl
#    
#    mode = IFF_TAP | IFF_NO_PI
#    TUNSETIFF = 0x400454ca

#    tun = os.open(tun_device_filename, os.O_RDWR)
#    ifs = ioctl(tun, TUNSETIFF, struct.pack("16sH", "gr%d", mode))
#    ifname = ifs[:16].strip("\x00")
#    return (tun, ifname)
    

# /////////////////////////////////////////////////////////////////////////////
#                             the flow graph
# /////////////////////////////////////////////////////////////////////////////

class usrp_graph(gr.top_block):
    def __init__(self, callback, options):
        gr.top_block.__init__(self)

        self._tx_freq            = options.tx_freq         # tranmitter's center frequency
        self._tx_gain            = options.tx_gain         # transmitter's gain
        #self._tx_subdev_spec     = options.tx_subdev_spec  # daughterboard to use
        #updated 2011 May 27, MR
        self._samp_rate			 = options.samp_rate	   # sample rate for USRP
        #self._interp             = options.interp          # interpolating rate for the USRP (prelim)
        self._rx_freq            = options.rx_freq         # receiver's center frequency
        self._rx_gain            = options.rx_gain         # receiver's gain
        #self._rx_subdev_spec     = options.rx_subdev_spec  # daughterboard to use
        #self._decim              = options.decim           # Decimating rate for the USRP (prelim)
        #updated 2011 May 27, MR
        #self._fusb_block_size    = options.fusb_block_size # usb info for USRP
        #self._fusb_nblocks       = options.fusb_nblocks    # usb info for USRP

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

        # copy the final answers back into options for use by modulator
        #options.bitrate = self._bitrate

        self.txpath = transmit_path(options)
        self.rxpath = receive_path(callback, options)

        self.connect(self.txpath, self.u_snk)
        self.connect(self.u_src, self.rxpath)

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
        #updated 2011 May 27, MR
        self.u_snk = uhd.usrp_sink(device_addr="", io_type=uhd.io_type.COMPLEX_FLOAT32, num_channels=1)
        self.u_snk.set_samp_rate(self._samp_rate) 
        
        self.u_snk.set_subdev_spec("", 0)
        #self.u_snk = usrp.sink_c(fusb_block_size=self._fusb_block_size,
        #                         fusb_nblocks=self._fusb_nblocks)
        #self.u_snk.set_interp_rate(self._interp)

        # determine the daughterboard subdevice we're using
        #if self._tx_subdev_spec is None:
        #    self._tx_subdev_spec = usrp.pick_tx_subdevice(self.u_snk)
        #self.u_snk.set_mux(usrp.determine_tx_mux_value(self.u_snk, self._tx_subdev_spec))
        #self.subdev = usrp.selected_subdev(self.u_snk, self._tx_subdev_spec)

        # Set the USRP for maximum transmit gain
        # (Note that on the RFX cards this is a nop.)
        #self.set_gain(self.subdev.gain_range()[1])
        g = self.u_snk.get_gain_range()
        #set the gain to the midpoint if it's currently out of bounds
        if self._tx_gain > g.stop() or self._tx_gain < g.start():
        	self._tx_gain = (g.stop() + g.start()) / 2
        self.u_snk.set_gain(self._tx_gain)

        # enable Auto Transmit/Receive switching
        #self.set_auto_tr(True)

    def _setup_usrp_source(self):
    	#updated 2011 May 27, MR
    	self.u_src = uhd.usrp_source(device_addr="", io_type=uhd.io_type.COMPLEX_FLOAT32,
    							 num_channels=1)
    	self.u_src.set_antenna("TX/RX", 0)
    							 
    	self.u_src.set_subdev_spec("",0)
        #self.u_src = usrp.source_c (fusb_block_size=self._fusb_block_size,
        #                        fusb_nblocks=self._fusb_nblocks)
        #adc_rate = self.u_src.adc_rate()

        #self.u_src.set_decim_rate(self._decim)
        self.u_src.set_samp_rate(self._samp_rate)
        
        g = self.u_src.get_gain_range()
        #set the gain to the midpoint if it's currently out of bounds
        if self._rx_gain > g.stop() or self._rx_gain < g.start():
        	self._rx_gain = (g.stop() + g.start()) / 2
        self.u_src.set_gain(self._rx_gain)

        # determine the daughterboard subdevice we're using
        #if self._rx_subdev_spec is None:
        #    self._rx_subdev_spec = usrp.pick_rx_subdevice(self.u_src)
        #self.subdev = usrp.selected_subdev(self.u_src, self._rx_subdev_spec)

        #what was the following line even supposed to do?
        #self.u_src.set_mux(usrp.determine_rx_mux_value(self.u_src, self._rx_subdev_spec))

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
        #updated 2011 May 27, MR
        #TODO: ensure that the correct index is chosen for these two
        r_snk = self.u_snk.set_center_freq(target_freq, 0)
        r_src = self.u_src.set_center_freq(target_freq, 0)
        #r_snk = self.u_snk.tune(self.subdev.which(), self.subdev, target_freq)
        #r_src = self.u_src.tune(self.subdev.which(), self.subdev, target_freq)
        if r_snk and r_src:
            return True

        return False
    
    #removed 2011 June 10, MR
    #def set_snk_gain(self, gain):
    #    """
    #    Sets the analog gain in the USRP
    #    """
    #    self.gain = gain
    #    #updated 2011 May 26, MR
    #    #TODO: ensure that the correct index is chosen for these two
    #    self.u_snk.set_gain(gain, 0)
    #    #self.subdev.set_gain(gain)

	#removed 2011 May 27, MR
    #def set_auto_tr(self, enable):
    #    """
    #    Turns on auto transmit/receive of USRP daughterboard (if exits; else ignored)
    #    """
    #    return self.subdev.set_auto_tr(enable)
        
    #def interp(self):
    #    return self._interp

    def add_options(normal, expert):
        """
        Adds usrp-specific options to the Options Parser
        """
        add_freq_option(normal)
        #normal.add_option("-T", "--tx-subdev-spec", type="subdev", default=None,
        #                  help="select USRP Tx side A or B")
        normal.add_option("-v", "--verbose", action="store_true", default=False)
        expert.add_option("", "--rx-freq", type="eng_float", default=None,
                          help="set Rx frequency to FREQ [default=%default]", metavar="FREQ")
        expert.add_option("", "--tx-freq", type="eng_float", default=None,
                          help="set Tx frequency to FREQ [default=%default]", metavar="FREQ")
        #updated 2011 May 27, MR
        expert.add_option("-s", "--samp_rate", type="intx", default=1000000,
        				   help="set sample rate for USRP to SAMP_RATE [default=%default]")
        #expert.add_option("-i", "--interp", type="intx", default=256,
        #                  help="set fpga interpolation rate to INTERP [default=%default]")
        #normal.add_option("-R", "--rx-subdev-spec", type="subdev", default=None,
        #                  help="select USRP Rx side A or B")
        normal.add_option("", "--rx-gain", type="eng_float", default=17, metavar="GAIN",
                          help="set receiver gain in dB [default=%default].  See also --show-rx-gain-range")
        normal.add_option("", "--show-rx-gain-range", action="store_true", default=False, 
                          help="print min and max Rx gain available")        
        normal.add_option("", "--tx-gain", type="eng_float", default=11.5, metavar="GAIN",
                          help="set transmitter gain in dB [default=%default].  See also --show-tx-gain-range")
        normal.add_option("", "--show-tx-gain-range", action="store_true", default=False, 
                          help="print min and max Tx gain available")
        #expert.add_option("-d", "--decim", type="intx", default=128,
        #                  help="set fpga decimation rate to DECIM [default=%default]")
        expert.add_option("", "--snr", type="eng_float", default=30,
                          help="set the SNR of the Rx channel in dB [default=%default]")
   
    # Make a static method to call before instantiation
    add_options = staticmethod(add_options)

    def _print_verbage(self):
        """
        Prints information about the transmit path
        """
        #print "Using TX d'board %s"    % (self.subdev.side_and_name(),)
        print "modulation:      %s"    % (self._modulator_class.__name__)
        #updated 2011 May 27, MR
        print "samp_rate		%3d"   % (self._samp_rate)
        #print "interp:          %3d"   % (self._interp)
        print "Tx Frequency:    %s"    % (eng_notation.num_to_str(self._tx_freq))
        
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
#                           Carrier Sense MAC
# /////////////////////////////////////////////////////////////////////////////

class cs_mac(object):
    """
    Prototype carrier sense MAC

    Reads packets from the TUN/TAP interface, and sends them to the PHY.
    Receives packets from the PHY via phy_rx_callback, and sends them
    into the TUN/TAP interface.

    Of course, we're not restricted to getting packets via TUN/TAP, this
    is just an example.
    """
    def __init__(self, verbose=False):
    	#updated by Morgan Redfield on 2011 May 16
    	#question: Do we need to implement address checking in the MAC?
    	#I haven't found any other location for node addresses.
    	#Also there are no MAC headers, and probably no PHY headers
    	#there probably isn't a node address at this point
        self.verbose = verbose
        self.tb = None             # top block (access to PHY)
        
        #control packet bookkeeping
        self.CTS_rcvd = False
        self.ACK_rcvd = False
        self.EOF_rcvd = False
        
        #data file to store measurements
        #filename = "CDMA_CA_experiment_" + time.strftime('%y%m%d_%H%M%S') + ".txt"
        #self.output_data_file = open(filename, 'w')
        
        #filename = "rcvd_packets_" + time.strftime('%y%m%d_%H%M%S') + ".txt"
        #self.rcvd_packets_file = open(filename, 'w')
        
        #delay time parameters
        #bus latency is also going to be a problem here
        self.SIFS_time = .005#.000028 #seconds
        self.DIFS_time = .020#.000128 #seconds
        self.ctl_pkt_time = .02#seconds. How long should this be?
        self.backoff_time_unit = .01#.000078 #seconds
        
        #measurement variables
        self.rcvd = 0
        self.rcvd_ok = 0
        self.sent = 0
    
    def __del__(self):
    	#self.output_data_file.close()
    	#self.rcvd_packets_file.close()
    	pass

    def set_flow_graph(self, tb):
        self.tb = tb

    def phy_rx_callback(self, ok, payload):
    	#updated by Morgan Redfield on 2011 May 16
        """
        Invoked by thread associated with PHY to pass received packet up.

        @param ok: bool indicating whether payload CRC was OK
        @param payload: contents of the packet (string)
        """
        #self.output_data_file.write("RCVD: %r\n" % ok)
        self.rcvd += 1

        if self.verbose:
            print "Rx: ok = %r  len(payload) = %4d" % (ok, len(payload))
            print payload
        if ok:
        	#question: is it possible that a packet sent from this function will 
        	#interfere with a packet sent from the main_loop function?
        	self.rcvd_ok += 1

        	#is this a ctl packet?
        	if payload == "ACK":
        		self.ACK_rcvd = True
        	elif payload == "RTS":
        		#wait for SIFS
        		self.MAC_delay(self.SIFS_time)
        		#only send the CTS signal if noone else is transmitting
        		if not self.tb.carrier_sensed():
        			self.tb.txpath.send_pkt("CTS")
        			self.sent += 1
        			#self.output_data_file.write("Sent: CTS\n")
        	elif payload == "CTS":
        		self.CTS_rcvd = True
        	else:
        		if payload == "EOF":
        			self.EOF_rcvd = True
	        	#wait for SIFS
	        	self.MAC_delay(self.SIFS_time)
    	    	#send ACK
    	    	#currently not affixing ACKS to other packets that are being sent
    	    	#this will probably cause latency issues
        		self.tb.txpath.send_pkt("ACK")
        		self.sent += 1
        		#self.output_data_file.write("Sent: ACK\n")
        		#self.rcvd_packets_file.write(payload + "\n")
	
    def DIFS(self):
    	#added by Morgan Redfield 2011 May 16
    	start_DIFS = time.clock()
    	while time.clock() - start_DIFS < self.DIFS_time:
    		if self.tb.carrier_sensed():
    			return False
    		#do spectrum sensing
    		pass #TODO: spectrum sense somehow
    	return True
    	
    def MAC_delay(self, delay_time):
    	#added by Morgan Redfield 2011 May 16
    	"""
    	Delay for a certain amount of time. Used instead of time.sleep()
    	
    	@param delay_time: number of seconds to delay for (can be fractional)
    	"""
    	start_delay = time.clock()
    	while time.clock() - start_delay < self.DIFS_time:
    		pass
    		
    def main_loop(self, num_packets):
    	#updated by Morgan Redfield on 2011 May 16
        """
        Main loop for MAC. This loop will generate and send num_packets worth of packets.
        It will then send an eof packet. The loop will exit when it has both sent and received
        an eof packet (to make sure the other node is also done sending).
        
        @param num_packets: number of packets to send before exiting loop

        FIXME: may want to check for EINTR and EAGAIN and reissue read
        """
        current_packet = 0
        while current_packet < num_packets:
            payload = time.strftime('%y%m%d_%H%M%S') + ", this is packet number " + str(current_packet)
            #self.output_data_file.write(payload)
            #self.output_data_file.write("\n")
            
            #if not payload:
            #    self.tb.txpath.send_pkt(eof=True)
            #    break

            #if self.verbose:
            #    print "Tx: len(payload) = %4d" % (len(payload),)
            
            #set up bookkeeping variables for CSMA/CA
            backoff_now = True
            backoff_time = 0
            packet_retries = 0 #start with max of 31 backoff time slots
            CWmin = 5 #figure out what this should be
            packet_lifetime = 5 #how many times should we try to send?
            #I set packet_lifetime pretty low because I don't think that we'll see a lot of
            #contention in this test. It seems like we'll be able to transmit the packet in only
            #a couple of tries
            
            #The frame has now been assembled, proceed to CSMA/CA algorithm
            #notes: no NAV is implemented
            #MAC frame is non-standard. It does not have proper headers.
            #there's no MAC level queue for packets right now
            
            #TODO: compute minimum quiet period
            
            #attempt to send the packet until we recieve an ACK or it's time to give up
            while not self.ACK_rcvd and packet_lifetime > packet_retries:
            	if current_packet == num_packets -1:
            		payload = "EOF"
            	#do the backoff now
            	if backoff_now:
            		backoff_now = False
            		#choose a random backoff time
            		backoff_time = random.randrange(0, 2**packet_retries * CWmin, 1)
            		#increment the packet_retries now that we've used it
            		#the next time we back off should have a longer delay time
            		if packet_retries < packet_lifetime: #make sure you don't extend the delay too far
	            		packet_retries = packet_retries + 1
            		#do the actual waiting
            		while backoff_time != 0:
            			self.DIFS()
            			while not self.tb.carrier_sensed() and backoff_time > 0:
            				self.MAC_delay(self.backoff_time_unit)
            				backoff_time = backoff_time - 1
            	
            	if not self.tb.carrier_sensed():
            		#send RTS
            		self.tb.txpath.send_pkt("RTS")
            		self.sent += 1
            		#self.output_data_file.write("Sent: RTS\n")
            		#wait for SIFS + CTS packet time
            		self.MAC_delay(self.SIFS_time + self.ctl_pkt_time)
            		if self.CTS_rcvd: 
            			#wait again for SIFS
            			self.MAC_delay(self.SIFS_time)
            			#reset CTS_rcvd
            			self.CTS_rcvd = False
            			self.tb.txpath.send_pkt(payload)
            			#self.output_data_file.write("Sent: data\n")
            			#wait for SIFS + ACK packet time
            			self.MAC_delay(self.SIFS_time + self.ctl_pkt_time)
            			self.sent += 1
            			#ACK should be true now, so the loop will exit
            		else: #otherwise we should backoff, right?
            			backoff_now = True
            	else: #wait for random backoff time
            		backoff_now = True
            #end while, packet sent or dropped
            
            #report packet loss
            if packet_lifetime == packet_retries:
            	#self.output_data_file.write("Failed to send packet")
            	pass
            else:
            	current_packet = current_packet + 1
            	
            #make sure that any recieved ACKs don't get confused with the next packet
            self.ACK_rcvd = False

        while not self.EOF_rcvd:
        	#just hang out until the other node is done
        	pass



# /////////////////////////////////////////////////////////////////////////////
#                                   main
# /////////////////////////////////////////////////////////////////////////////

def main():

    parser = OptionParser (option_class=eng_option, conflict_handler="resolve")
    expert_grp = parser.add_option_group("Expert")

    parser.add_option("-m", "--modulation", type="choice", choices=['bpsk', 'qpsk'],
                      default='bpsk',
                      help="Select modulation from: bpsk, qpsk [default=%%default]")
    parser.add_option("-v","--verbose", action="store_true", default=False)
    parser.add_option("-p","--packets", type="int", default = 40, 
    					  help="set number of packets to send [default=%default]")
    expert_grp.add_option("-c", "--carrier-threshold", type="eng_float", default=30,
                          help="set carrier detect threshold (dB) [default=%default]")

    usrp_graph.add_options(parser, expert_grp)
    transmit_path.add_options(parser, expert_grp)
    receive_path.add_options(parser, expert_grp)
    blks2.ofdm_mod.add_options(parser, expert_grp)
    blks2.ofdm_demod.add_options(parser, expert_grp)

    #removed 2011 May 27, MR
    #fusb_options.add_options(expert_grp)

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


    #removed 2011 May 27, MR
    # If the user hasn't set the fusb_* parameters on the command line,
    # pick some values that will reduce latency.

    #if options.fusb_block_size == 0 and options.fusb_nblocks == 0:
    #    if realtime:                        # be more aggressive
    #        options.fusb_block_size = gr.prefs().get_long('fusb', 'rt_block_size', 1024)
    #        options.fusb_nblocks    = gr.prefs().get_long('fusb', 'rt_nblocks', 16)
    #    else:
    #        options.fusb_block_size = gr.prefs().get_long('fusb', 'block_size', 4096)
    #        options.fusb_nblocks    = gr.prefs().get_long('fusb', 'nblocks', 16)
    
    #print "fusb_block_size =", options.fusb_block_size
    #print "fusb_nblocks    =", options.fusb_nblocks

    # instantiate the MAC
    mac = cs_mac(options.verbose)


    # build the graph (PHY)
    tb = usrp_graph(mac.phy_rx_callback, options)

    mac.set_flow_graph(tb)    # give the MAC a handle for the PHY

    #if fg.txpath.bitrate() != fg.rxpath.bitrate():
    #    print "WARNING: Transmit bitrate = %sb/sec, Receive bitrate = %sb/sec" % (
    #        eng_notation.num_to_str(fg.txpath.bitrate()),
    #        eng_notation.num_to_str(fg.rxpath.bitrate()))
             
    print "modulation:     %s"   % (options.modulation,)
    print "freq:           %s"      % (eng_notation.num_to_str(options.tx_freq))
    #print "bitrate:        %sb/sec" % (eng_notation.num_to_str(fg.txpath.bitrate()),)
    #print "samples/symbol: %3d" % (fg.txpath.samples_per_symbol(),)
    #print "interp:         %3d" % (fg.txpath.interp(),)
    #print "decim:          %3d" % (fg.rxpath.decim(),)

    tb.rxpath.set_carrier_threshold(options.carrier_threshold)
    print "Carrier sense threshold:", options.carrier_threshold, "dB"
    
    print
    #print "Allocated virtual ethernet interface: %s" % (tun_ifname,)
    #print "You must now use ifconfig to set its IP address. E.g.,"
    #print
    #print "  $ sudo ifconfig %s 192.168.200.1" % (tun_ifname,)
    #print
    #print "Be sure to use a different address in the same subnet for each machine."
    print


    tb.start()    # Start executing the flow graph (runs in separate threads)

    mac.main_loop(options.packets)    # don't expect this to return...
    
    #do stuff with the mac measurement results
    print "this node sent ", mac.sent, " packets"
    print "this node rcvd ", mac.rcvd, " packets"
    print "this node rcvd ", mac.rcvd_ok, " packets correctly"
	
    tb.stop()     # but if it does, tell flow graph to stop.
    tb.wait()     # wait for it to finish
    
    mac.__del__()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
