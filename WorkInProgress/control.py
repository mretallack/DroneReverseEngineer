#!/usr/bin/env python3
"""
Drone control sender using 0x6363 protocol
Based on Java_com_lewei_lib_LeweiLib_LW93SendUdpData from liblewei-2.3.so
Sends control packets to port 40000
"""

import socket
import time
import struct

DRONE_IP = "192.168.0.1"
DRONE_CONTROL_PORT = 40000  # Drone receives control on port 40000

def create_control_packet(right_x=0x80, right_y=0x80, left_y=0x80, left_x=0x80, 
                         trim_v=0x80, trim_r=0x80, trim_l=0x80, 
                         command=0x0c, mode=0x8c):
    """
    Create 0x6363 control packet based on native library implementation
    
    Protocol from Java_com_lewei_lib_LeweiLib_LW93SendUdpData:
    - Wraps control data with 7-byte header when vga_udp_t is active
    - Header: 0x6363 0x0a 0x00 [length_low] 0x00 [length_high]
    
    Control data (from SANROCK U61W analysis):
    right_x:  Right stick X (aileron) - neutral=0x80
    right_y:  Right stick Y (elevator) - neutral=0x80  
    left_y:   Left stick Y (throttle) - neutral=0x80
    left_x:   Left stick X (rudder) - neutral=0x80, range 0x2f-0xd0
    trim_v:   Trim vertical - base=0x80
    trim_r:   Trim right - base=0x80
    trim_l:   Trim left - base=0x80
    command:  0x0c=neutral, 0x1c=takeoff, 0x2c=land
    mode:     0x8c=low speed, 0x84=high speed, 0x8e=headless low, 0x86=headless high
    """
    # Control data payload (11 bytes)
    control_data = bytearray([
        0x66,      # Start of frame marker
        right_x,   # Right stick X (aileron)
        right_y,   # Right stick Y (elevator)
        left_y,    # Left stick Y (throttle)
        left_x,    # Left stick X (rudder)
        trim_v,    # Trim vertical
        trim_r,    # Trim right
        trim_l,    # Trim left
        command,   # Command byte
        mode,      # Mode byte
        0x99       # End of frame marker
    ])
    
    # Wrap with 7-byte 0x6363 header (as done in native code)
    data_len = len(control_data)
    packet = bytearray([
        0x63, 0x63,                    # Header
        0x0a,                          # Command type
        0x00,                          # Sequence
        data_len & 0xff,               # Length low byte
        0x00,                          # Reserved
        (data_len >> 8) & 0xff         # Length high byte
    ])
    packet.extend(control_data)
    
    return bytes(packet)

def send_control(sock, right_x=0x80, right_y=0x80, left_y=0x80, left_x=0x80, 
                command=0x0c, mode=0x8c):
    """Send control packet to drone"""
    packet = create_control_packet(right_x, right_y, left_y, left_x, 
                                   command=command, mode=mode)

    print(packet.hex())
    sock.sendto(packet, (DRONE_IP, DRONE_CONTROL_PORT))
    print(f"Sent: RX={right_x:02x} RY={right_y:02x} LY={left_y:02x} LX={left_x:02x} CMD={command:02x} MODE={mode:02x}")

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print(f"Sending control to {DRONE_IP}:{DRONE_CONTROL_PORT}")
    print("Protocol: 0x6363 (VGA camera control)")
    print("Neutral position: all sticks at 0x80")
    print("Sending every 50ms (as per native code)\n")
    
    try:
        count = 0
        while True:
            # Send neutral position every 50ms (matching native implementation)
            send_control(sock)
            count += 1
            
            # Print status every 20 packets (1 second)
            if count % 20 == 0:
                print(f"Sent {count} packets...")
            
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        sock.close()

if __name__ == '__main__':
    main()
