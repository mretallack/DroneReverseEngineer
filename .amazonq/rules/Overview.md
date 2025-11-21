I am trying to decode a stream from a drone.

I have decompile the core of the android app and it uses a so lib to do the handling:

tools/App/project/liblewei-2.3.so.c

this is the original code. details of how it works is stored in the following file, make sure this file is up to date when new information is found:

tools/App/project/README.md

com.lewei.multiple.app.Rudder component does:

Control Flow
The Rudder custom view handles touch events and triggers the following chain:

Rudder View (com.lewei.multiple.app.Rudder)

Captures touch input from the joystick overlay

Converts touch coordinates to control values (throttle, rudder, aileron, elevator)

Values are normalized to 0x80 (neutral) with range typically 0x2f-0xd0

Java Control Loop

Runs in a thread sending commands every 50ms

Calls: LeweiLib.LW93SendUdpData(byte[] data, int length)

Native Library (liblewei-3.2.2.so)

Function: Java_com_lewei_lib_LeweiLib_LW93SendUdpData (line 9455)

Constructs 0x6363 control packet:

0x6363 [header]
0x0a [command byte]
0x66 [frame start]
[Right stick X] [Right stick Y] [Left stick Y] [Left stick X]
[Trim values]
[Command byte: 0x0c=neutral, 0x1c=takeoff, 0x2c=land]
[Mode byte: 0x8c=low speed, 0x84=high speed]
0x99 [frame end]

Copy
Calls sendto() to UDP port 40000 on the drone


make sure this file is up to date when new information is

The new python version of the app is:

/stream_video.py


The drone exposes two UDP ports:

40000/udp
49153/udp

40000 has the video from the drone, the app sends a command and the drone replies with the video stream in JPEG format.

## Video Stream Initialization

Before the drone sends video, the app must send an initialization packet:

From vga_send_command_thread (line 16152 in liblewei-2.3.so.c):
- Sends 0x6363 0x01 packet every 1000ms (1 second) until video starts
- This is the "start video" command
- Packet structure: 0x6363 0x01 0x00 [length] 0x00 0x00 0x00
- Sent to port 40000 on the drone

The thread continuously sends this until the drone responds with video packets.

