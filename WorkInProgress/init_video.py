#!/usr/bin/env python3
"""
Send video initialization command to drone
Based on vga_send_command_thread from liblewei-2.3.so.c line 16152
"""

import socket
import time

DRONE_IP = "192.168.0.1"
DRONE_PORT = 40000

def create_video_start_packet():
    """
    Create 0x6363 video start command
    From vga_send_command_thread:
    uStack_434 = CONCAT13(uStack_434._3_1_,0x10000);
    uStack_434 = CONCAT22(uStack_434._2_2_,0x6363);
    
    This creates: 0x6363 0x01 0x00 [length] 0x00 0x00 0x00
    """
    packet = bytearray([
        0x63, 0x63,  # Header
        0x01,        # Command type: Start video
        0x00,        # Sequence
        0x00,        # Length low
        0x00,        # Reserved
        0x00         # Length high
    ])
    return bytes(packet)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print(f"Sending video initialization to {DRONE_IP}:{DRONE_PORT}")
    print("This enables the drone to start sending video stream")
    print("Sending every 1 second (as per native code)...\n")
    
    try:
        count = 0
        while True:
            packet = create_video_start_packet()
            sock.sendto(packet, (DRONE_IP, DRONE_PORT))
            count += 1
            print(f"Sent video start command #{count}: {packet.hex()}")
            time.sleep(1.0)  # Send every 1000ms as per native code
            
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        sock.close()

if __name__ == '__main__':
    main()
