# /////////////////////////////////////////////////////////////////////////////
#                           Carrier Sense MAC
#
# FuNLab
# University of Washington
# Morgan Redfield
#
# Implement a CSMA CA MAC. Note that this is not 802.11 (not even close).
# Currently the MAC just generates its own packets. Eventually this might be tied
# in with TUN/TAP.
#
# Addressing in this MAC is super kludgy. I'm basically just prepending a character
# to every packet that I send and using that as an address. The return address is
# apended to the end of the packet. I'm reserving 
# the characters 'x', 'y', and 'z' for special functions.
# 'x' is a broadcast packet (all packets are broadcast for now
# 'y', and 'z' are for future applications
#
# ToDo:
# I'm using RTS/CTS with broadcast packets, that can't work with more than 2 nodes
# figure out delay time parameters (minimize)
# TUN/TAP
# /////////////////////////////////////////////////////////////////////////////

import time
import random

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
    def __init__(self, options):
        #updated by Morgan Redfield on 2011 May 16
        self.verbose = options.verbose
        self.tb = None             # top block (access to PHY)
        
        #control packet bookkeeping
        self.CTS_rcvd = False
        self.ACK_rcvd = False
        self.EOF_rcvd = False
        self.RTS_rcvd = False
        
        self.address = options.address
        
        #delay time parameters
        #bus latency is also going to be a problem here
        self.SIFS_time = options.sifs
        self.DIFS_time = options.difs
        self.ctl_pkt_time = options.ctl
        self.rnd_trip_time = options.rnd_trip
        self.backoff_time_unit = options.backoff
        
        #measurement variables
        self.current_packet
        self.rcvd = 0
        self.rcvd_ok = 0
        self.sent = 0
        self.rcvd_data = 0
        self.rcvd_pkts = []
        self.sent_pkts = []

    def set_flow_graph(self, tb):
        self.tb = tb

    def phy_rx_callback(self, ok, payload):
        #updated by Morgan Redfield on 2011 May 16
        """
        Invoked by thread associated with PHY to pass received packet up.

        @param ok: bool indicating whether payload CRC was OK
        @param payload: contents of the packet (string)
        """
        #if the rcvd packet is empty or from this node, ignore it completely
        if len(payload) == 0 or (payload[1] == self.address):
            return
            
        #self.rcvd isn't very accurate because it may contain corrupted packets
        #from this node. It may also miss severely corrupted (len = 0) packets from
        #other nodes.
        self.rcvd += 1

        if self.verbose:
            print "Rx: ok = %r  len(payload) = %4d" % (ok, len(payload))
        if ok:
            sender = payload[1]
            payload = payload[2:]
            #question: is it possible that a packet sent from this function will 
            #interfere with a packet sent from the main_loop function?
            self.rcvd_ok += 1
            if self.verbose:
                print "RX: ", payload

            #is this a ctl packet?
            if len(payload) == 3:
	            if payload == "RTS":
    	            #wait for SIFS
        	        self.RTS_rcvd = True
            	    self.MAC_delay(self.SIFS_time)
                	#only send the CTS signal if noone else is transmitting
                	if not self.tb.carrier_sensed():
                	    self.tb.txpath.send_pkt(sender + self.address + "CTS")
                    	self.sent += 1
            	elif payload == "CTS":
                	self.CTS_rcvd = True
                #else something strange has happened
            elif payload[3:] == "ACK":
                self.ACK_rcvd = True
                self.RTS_rcvd = False
                self.sent_pkts.append(payload[:3])
                self.current_packet += 1
            else:
                self.rcvd_data += 1
                self.rcvd_pkts.append(int(payload[:3]))
                if payload[3:] == "EOF":
                    self.EOF_rcvd = True
                #wait for SIFS
                self.MAC_delay(self.SIFS_time)
                #send ACK
                #currently not affixing ACKS to other packets that are being sent
                #this will probably cause latency issues
                self.tb.txpath.send_pkt(sender + self.address + payload[:3] + "ACK")
                self.RTS_rcvd = False
                self.sent += 1
    
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
            
    def generate_next_packet():
    	"""
    	Generate the next packet to send
    	"""
        payload = str(self.current_packet).zfill(3) + time.strftime('%y%m%d_%H%M%S') + ", this is packet number " + str(self.current_packet)
        if self.current_packet >= num_packets
        	payload = str(self.current_packet).zfill(3) + "EOF"
        return payload
    
    def main_loop(self, num_packets):
        """
        Main loop for MAC. This loop will generate and send num_packets worth of packets.
        It will then send an eof packet. The loop will exit when it has both sent and received
        an eof packet (to make sure the other node is also done sending).
        
        @param num_packets: number of packets to send before exiting loop
        """
        done = False
        current_packet = 0
        while not done:
            payload = None
            #the following is for TUN
            #payload = os.read(self.tun_fd, 10*1024)
            
            payload = generate_next_packet()
            
            if self.verbose and payload:
                print "packet: ", payload
                #print "Tx: len(payload)=", len(payload)
            
            #set up bookkeeping variables for CSMA/CA
            backoff_now = True
            backoff_time = 0
            packet_retries = 0 #start with max of 31 backoff time slots
            CWmin = 5
            packet_lifetime = 5
                                    
            #attempt to send the packet until we recieve an ACK or it's time to give up
            while payload and not self.ACK_rcvd and packet_lifetime > packet_retries:
                #do the backoff
                if backoff_now:
                    backoff_now = False
                    #choose a random backoff time
                    backoff_time = random.randrange(0, 2**packet_retries * CWmin, 1)
                    #increment the packet_retries now that we've used it
                    #the next time we back off should have a longer delay time
                    packet_retries += 1
                    #do the actual waiting
                    while backoff_time != 0:
                        while not self.DIFS():
                            pass #self.DIFS() returns false if the carrier is sensed active
                        while not self.tb.carrier_sensed() and backoff_time > 0:
                            self.MAC_delay(self.backoff_time_unit)
                            backoff_time = backoff_time - 1
                
                #done with backoff, now try sending data
                if self.RTS_rcvd:
                    #if we expect to rcv data and ack packets, don't transmitting
                    start_delay = time.clock()
                    while time.clock() - start_delay < self.rnd_trip_time:
                        if not self.RTS_rcvd:
                            start_delay = 0
                    self.RTS_rcvd = False
                elif not self.tb.carrier_sensed(): #the spectrum isn't busy or expected to be busy
                    self.tb.txpath.send_pkt('x' + self.address + "RTS")
                    self.sent += 1
                    self.MAC_delay(self.SIFS_time + self.ctl_pkt_time)
                    if self.CTS_rcvd: 
                        self.MAC_delay(self.SIFS_time)
                        self.CTS_rcvd = False
                        self.tb.txpath.send_pkt('x' + self.address + payload)
                        #wait for SIFS + ACK packet time
                        self.MAC_delay(self.SIFS_time + self.ctl_pkt_time)
                        self.sent += 1
                        #ACK should be true now, so the loop will exit
                    else: #we're not clear to send, so wait again
                        backoff_now = True
                else: #the spectrum's busy, so wait again
                    backoff_now = True
            #end while, packet sent or dropped
            
            #report packet loss
            if packet_lifetime < packet_retries:
                self.current_packet = self.current_packet + 1
                
            #make sure that any recieved ACKs don't get confused with the next packet
            self.ACK_rcvd = False

        #while not self.EOF_rcvd:
        #    #just hang out until the other node is done
        #    time.sleep(1)
        
    def add_options(normal, expert):
        """
        Adds MAC-specific options to the Options Parser
        """
        expert.add_option("", "--sifs", type="eng_float", default=.0001,
                          help="set SIFS time [default=%default]")
        expert.add_option("", "--difs", type="eng_float", default=.005,
                          help="set DIFS time [default=%default]")
        expert.add_option("", "--ctl", type="eng_float", default=.01,
                          help="set control packet time [default=%default]")
        expert.add_option("", "--rnd-trip", type="eng_float", default=.03,
                          help="set round trip time for RTS-CTS-data [default=%default]")
        expert.add_option("", "--backoff", type="eng_float", default=.01,
                          help="set backoff time [default=%default]")
    # Make a static method to call before instantiation
    add_options = staticmethod(add_options)