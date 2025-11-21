#!/usr/bin/env python3
"""
Interactive drone control using 0x6363 protocol
Based on Java_com_lewei_lib_LeweiLib_LW93SendUdpData
"""

import socket
import time
import sys
import select

DRONE_IP = "192.168.0.1"
DRONE_CONTROL_PORT = 40000

def create_control_packet(right_x=0x80, right_y=0x80, left_y=0x80, left_x=0x80, 
                         trim_v=0x80, trim_r=0x80, trim_l=0x80, 
                         command=0x0c, mode=0x8c):
    """Create 0x6363 control packet"""
    control_data = bytearray([
        0x66,      # Start marker
        right_x,   # Right stick X (aileron)
        right_y,   # Right stick Y (elevator)
        left_y,    # Left stick Y (throttle)
        left_x,    # Left stick X (rudder)
        trim_v, trim_r, trim_l,
        command,   # 0x0c=neutral, 0x1c=takeoff, 0x2c=land
        mode,      # 0x8c=low speed, 0x84=high speed
        0x99       # End marker
    ])
    
    data_len = len(control_data)
    packet = bytearray([
        0x63, 0x63, 0x0a, 0x00,
        data_len & 0xff, 0x00, (data_len >> 8) & 0xff
    ])
    packet.extend(control_data)
    return bytes(packet)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Control state
    right_x = 0x80  # Aileron (roll)
    right_y = 0x80  # Elevator (pitch)
    left_y = 0x80   # Throttle
    left_x = 0x80   # Rudder (yaw)
    command = 0x0c  # Neutral
    mode = 0x8c     # Low speed
    
    print(f"Drone Control - {DRONE_IP}:{DRONE_CONTROL_PORT}")
    print("\nControls:")
    print("  W/S - Throttle up/down (left stick Y)")
    print("  A/D - Rudder left/right (left stick X)")
    print("  I/K - Pitch forward/back (right stick Y)")
    print("  J/L - Roll left/right (right stick X)")
    print("  T - Takeoff (command=0x1c)")
    print("  G - Land (command=0x2c)")
    print("  H - Toggle speed (0x8c/0x84)")
    print("  R - Reset to neutral")
    print("  Q - Quit\n")
    
    # Set stdin to non-blocking
    import termios, tty
    old_settings = termios.tcgetattr(sys.stdin)
    
    try:
        tty.setcbreak(sys.stdin.fileno())
        
        while True:
            # Check for keyboard input
            if select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1).lower()
                
                if key == 'q':
                    break
                elif key == 'w':
                    left_y = min(0xd0, left_y + 10)
                elif key == 's':
                    left_y = max(0x2f, left_y - 10)
                elif key == 'a':
                    left_x = max(0x2f, left_x - 10)
                elif key == 'd':
                    left_x = min(0xd0, left_x + 10)
                elif key == 'i':
                    right_y = min(0xd0, right_y + 10)
                elif key == 'k':
                    right_y = max(0x2f, right_y - 10)
                elif key == 'j':
                    right_x = max(0x2f, right_x - 10)
                elif key == 'l':
                    right_x = min(0xd0, right_x + 10)
                elif key == 't':
                    command = 0x1c  # Takeoff
                    print("TAKEOFF command")
                elif key == 'g':
                    command = 0x2c  # Land
                    print("LAND command")
                elif key == 'h':
                    mode = 0x84 if mode == 0x8c else 0x8c
                    print(f"Speed: {'HIGH' if mode == 0x84 else 'LOW'}")
                elif key == 'r':
                    right_x = right_y = left_x = left_y = 0x80
                    command = 0x0c
                    print("Reset to neutral")
            
            # Send control packet every 50ms
            packet = create_control_packet(right_x, right_y, left_y, left_x, 
                                          command=command, mode=mode)
            print(packet.hex())
            sock.sendto(packet, (DRONE_IP, DRONE_CONTROL_PORT))
            
            # Reset command to neutral after sending takeoff/land
            if command != 0x0c:
                command = 0x0c
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        sock.close()

if __name__ == '__main__':
    main()
