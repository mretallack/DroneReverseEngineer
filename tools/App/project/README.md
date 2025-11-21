# Drone Video Stream Protocol Analysis

Reverse engineering analysis of `liblewei-3.2.2.so` native library from LW FPV Android app.

## Overview

The library supports **TWO different camera protocols**:
1. **HD Camera**: "lewei_cmd" protocol (higher quality)
2. **VGA Camera**: 0x6363 protocol (cheaper drones like SANROCK U61W)

## HD Camera Protocol ("lewei_cmd")

### UDP Receive Function
**Location**: Line 8211 in `liblewei-3.2.2.so.c`

```c
undefined8 Java_com_lewei_lib_LeweiLib_LW93RecvUdpData(long *param_1)
{
    // Receives max 1024 bytes (0x400) per packet
    uVar2 = recvfrom(DAT_001c200c, &DAT_001c28c0, 0x400, 0, 
                     (sockaddr *)&DAT_001c2890, &DAT_001c2010);
    
    // Copies to Java byte array
    memcpy(__dest, &DAT_001c28c0, (long)iVar1);
    return uVar3;
}
```

### Packet Structure
**Location**: Lines 9780-9850

```
Offset 0x00-0x08: "lewei_cmd" header (9 bytes)
Offset 0x0C:      Command type (0x101=video, 0x103=MJPEG)
Offset 0x00:      Frame counter (4 bytes)
Offset 0x04:      Data length (4 bytes)
Offset 0x08:      Timestamp (8 bytes)
Offset 0x10:      Frame type (0x01 = first packet)
Offset 0x20:      JPEG data start ← KEY OFFSET
```

**Important**: The 0x20 offset matches Wireshark captures:
- Wireshark shows data at 0x62
- 0x62 = 0x42 (UDP header) + 0x20 (packet header)

### Frame Assembly
**Location**: Line 9980

```c
// Extract JPEG data starting at offset 0x20
__ptr = (void *)save_stream_photo(&DAT_001c2d40, auStack_7c, 
                                  __src + 0x20,  // JPEG data pointer
                                  local_88[0]);   // Data length
```

### Save Function
**Location**: Line 8581

```c
void save_stream_photo(undefined8 param_1, undefined8 param_2, 
                       void *param_3,  // JPEG data
                       int param_4)    // Data length
{
    // Writes raw JPEG data to file
    fwrite(param_3, (long)param_4, 1, __s_00);
}
```

## VGA Camera Protocol (0x6363)

### Function Summary Table

| Function | Line | Purpose |
|----------|------|----------|
| `vga_create_udp()` | 14837 | Create and bind UDP socket |
| `vga_close_udp()` | 14922 | Close UDP socket |
| `vga_send_udp()` | 14944 | Send UDP packet (wrapper for sendto) |
| `vga_recv_udp()` | 15184 | Receive UDP packet (wrapper for recvfrom) |
| `vga_send_command_thread()` | 14957 | Thread: Send 0x6363 control packets |
| `vga_read_buffer_thread()` | 15196 | Thread: Receive and process 0x6363 video |

### VGA UDP Functions

**Core Functions**:
- `vga_create_udp()` - Line 14837: Create UDP socket
- `vga_close_udp()` - Line 14922: Close UDP socket  
- `vga_send_udp()` - Line 14944: Send UDP packet
- `vga_recv_udp()` - Line 15184: Receive UDP packet
- `vga_send_command_thread()` - Line 14957: Command sending thread (0x6363 control packets)
- `vga_read_buffer_thread()` - Line 15196: Video receive thread (0x6363 video packets)

### VGA Send Function
**Location**: Line 14944

```c
void vga_send_udp(int param_1, void *param_2, int param_3)
{
    DAT_001c409e = 0x409c;
    sendto(param_1, param_2, (long)param_3, 0, 
           (sockaddr *)&DAT_001c409c, DAT_001c40ac);
}
```

### VGA Receive Function  
**Location**: Line 15184

```c
void vga_recv_udp(int param_1, void *param_2, int param_3)
{
    recvfrom(param_1, param_2, (long)param_3, 0, 
             (sockaddr *)&DAT_001c409c, &DAT_001c40ac);
}
```

**Called at line 15289**: `vga_recv_udp(vga_udp_t, &local_7d8, 2000)`
- Receives up to 2000 bytes into stack starting at `&local_7d8`
- JPEG data payload is at `auStack_7a2` = `&local_7d8 + 0x36` (54 bytes offset)

### Packet Detection
**Location**: Line 15433 (inside `vga_read_buffer_thread`)

```c
if (local_7d8 == 0x6363) {
    // VGA camera packet detected
}
```

### Packet Structure

```
Offset 0x00-0x01: 0x6363 header (2 bytes)
Offset 0x02:      Command type
Offset 0x03:      Packet length
Offset 0x04-0x35: Header/metadata (50 bytes)
Offset 0x36 (54): JPEG data start (0xFFD8 JPEG header)
```

**Important**: JPEG data starts at byte 54 (0x36), not immediately after the packet header.

### VGA Read Buffer Thread
**Location**: Line 15196 - Main video receive loop

This thread:
1. Calls `vga_recv_udp()` to receive packets
2. Checks for 0x6363 header at line 15433
3. Processes different command types (0x01, 0x09, 0x0B)
4. Extracts and decodes video data

### Command Types
**Location**: Lines 15300-15480 (inside `vga_read_buffer_thread`)

The function handles 4 different command paths:

1. **Multi-Packet Video** (cmd_type = 0x03) - Line 15300:
   ```c
   if (local_7d6 == '\x03') {
       // Multi-packet frame assembly
       // Uses two buffers (__s and __s_00) for double buffering
       // Tracks packet sequence and reassembles complete frame
   }
   ```

2. **Heartbeat** (cmd_type = 0x01, length = 99) - Line 15433:
   ```c
   if (local_7d6 == '\x01') {
       if (local_7d8 == 0x6363) {
           if (local_7d3 == 99) {
               // 99-byte heartbeat packet
               pvVar28 = memcpy(&DAT_001c3ff8, &local_7d1, 99);
           }
       }
   }
   ```

3. **Key Events** (cmd_type = 0x09) - Line 15460:
   ```c
   if (local_7d6 == '\t') {  // 0x09
       if ((local_7d8 == 0x6363) && (DAT_001c405c != local_7d5)) {
           // Key event handling
       }
   }
   ```

4. **Single Video Data** (cmd_type = 0x0B) - Line 15470:
   ```c
   if ((local_7d6 != '\v') || (local_7d8 != 0x6363)) goto LAB_00123c98;  // 0x0B
   uVar1 = local_7d3 - 7;  // Data length minus 7-byte header
   memcpy(pvVar28, &local_7d1, (long)(int)uVar1);  // Data starts at offset 7
   ```
   
   **Note**: While the C code shows data at offset 7, actual JPEG data (0xFFD8 header) 
   is at offset 54 (0x36) in the UDP packet. The intermediate bytes (7-53) contain 
   frame metadata and packet structure information.

2. **Heartbeat** (cmd_type = 0x01, length = 99):
   ```c
   if (local_7d8 == 0x6363) {
       if (local_7d3 == 99) {
           pvVar28 = memcpy(&DAT_001c3ff8, &local_7d1, 99);
       }
   }
   ```

3. **Key Events** (cmd_type = 0x09):
   ```c
   if ((local_7d8 == 0x6363) && (DAT_001c405c != local_7d5)) {
       _DAT_001c4060 = CONCAT11((byte)uStack_7d0, local_7d1);
   }
   ```

### Video Data Extraction

**JPEG Data Location**: Byte 54 (0x36) in UDP packet
- First 2 bytes at offset 54: `0xFF 0xD8` (JPEG SOI marker)
- Last 2 bytes of frame: `0xFF 0xD9` (JPEG EOI marker)

### VGA Data Obfuscation (Optional)

Some VGA cameras use simple data obfuscation. The code checks `local_7af` (frame type flag):

**Line 15328-15332**: If `cVar14 == 0x81` (hardware encoded):
```c
if (cVar14 == -0x7f) {  // 0x81 as signed char
    LW_Decode_New(data + (length >> 1), width, height, format);
}
```

**Line 15333-15336**: If `cVar14 != 0x02` (obfuscated):
```c
else if (cVar14 != '\x02') {
    iVar21 = encode_index(uVar1, data_length);
    data[iVar21] = ~data[iVar21];  // Bit flip at calculated index
}
```

This is **simple obfuscation** - flips bits at a specific index. Most modern cameras send unobfuscated JPEG data (flag = 0x02) and don't need this decoding.

**Packet Structure Summary** (from `vga_read_buffer_thread` line 15289):

Data received into `&local_7d8`, JPEG payload in `auStack_7a2`:

```
Offset  Variable      Size  Description
------  -----------   ----  -----------
0x00    local_7d8     2     0x6363 (VGA header)
0x02    local_7d6     1     Command type (0x01/0x03/0x09/0x0B)
0x03    local_7d5     2     Sequence/packet ID
0x05    local_7d3     2     Packet length
0x07    local_7d1     1     Frame type/flags
0x08    uStack_7d0    4     Frame ID
0x0C    local_7cc     4     Metadata
0x10    local_7c8     4     Metadata
0x14    local_7c4     2     Metadata
0x16    local_7be     1     Metadata
0x17    local_7bd     1     Metadata
0x18    local_7bc     2     Metadata
0x1A    local_7ba     2     Metadata
0x1C    local_7b8     1     Metadata
0x1D    local_7b7     1     Metadata
0x1E    local_7b6     1     Metadata
0x1F    local_7b5     1     Metadata
0x20    local_7af     1     Metadata
0x21    local_7ae     2     Metadata
0x23    local_7ac     2     Metadata
0x25    local_7aa     2     Metadata
0x27    local_7a8     2     Metadata
0x29    local_7a6     2     Metadata
0x2B    local_7a4     2     Metadata
0x36    auStack_7a2   1946  JPEG data payload (starts with 0xFFD8)
```

**Key Finding**: `auStack_7a2` is at offset **0x36 (54 bytes)** from `local_7d8`.
This is confirmed by line 15304: `memcpy(__s + ... + 0x40c, auStack_7a2, ...)`

## Control Packet Protocol (0x6363)

### VGA Send Command Thread
**Location**: Line 14957

Sends 0x6363 control packets every 50ms:
- Line 15012: Video start command (cmd_type = 0x01)
- Line 15043: WiFi SSID command (cmd_type = 0x04/0x06)
- Line 15063: WiFi password command (cmd_type = 0x07/0x0D)
- Line 15090: Clear WiFi command (cmd_type = 0x0C)
- Line 15100: Camera LED on (cmd_type = 0x0F)
- Line 15110: Camera LED off (cmd_type = 0x10)

### HD Send Function
**Location**: Line 8165 - `Java_com_lewei_lib_LeweiLib_LW93SendUdpData`

```c
// Construct 0x6363 control packet
DAT_001c28b8._0_2_ = 0x6363;  // Header
DAT_001c28b8._2_1_ = 10;      // Command byte
*__dest = 0xa6363;            // Packed header
memcpy((void *)((long)__dest + 7), __src, __n);  // Control data
sendto(__fd, __dest, __n + 7, 0, ...);
```

### Control Packet Structure (from SANROCK U61W analysis)

```
Byte Position:
63 63 0a 00 00 0b 00 66 80 80 80 80 80 80 80 0c 8c 99
aa ab ac ad ae af ag ah ai aj ak al am an ao ap aq ar

aa-ab: 0x6363 - Start of message
ac-ag: Command bytes
ah:    0x66 - Start of frame
ai:    Right stick X (neutral = 0x80)
aj:    Right stick Y (neutral = 0x80)
ak:    Left stick Y (neutral = 0x80)
al:    Left stick X (neutral = 0x80, range 0x2f-0xd0)
am:    Trim vertical (base = 0x80)
an:    Trim right (base = 0x80)
ao:    Trim left (base = 0x80)
ap:    Command (0x0c=neutral, 0x1c=takeoff, 0x2c=land)
aq:    Mode byte (0x8c=low speed, 0x84=high speed, 0x8e=headless low, 0x86=headless high)
ar:    0x99 - End of frame
```

## Network Configuration

### Ports
- **Port 6000**: Host receives video (from drone port 40000)
- **Port 5010**: Host sends control (to drone port 40000)
- **Port 40000**: Drone sends/receives (bidirectional)

### Video Stream Initialization
**Location**: Line 355 in `LWAPIManeger.java`

```java
if (LeweiLib.LW93StartLiveStream(1, i) == 1) {
    // Stream started successfully
}
```

Native implementation sends `LEWEI_CMD_STARTVIDEO` command via `send_stream_cmd()`.

## Frame Assembly Process

### HD Camera
1. Receive packets (max 1024 bytes each)
2. Extract JPEG data from offset 0x20
3. Assemble ~1080 packets per frame
4. Last packet is smaller than 1080 bytes
5. Add JPEG end marker (0xFFD9) if missing

### VGA Camera
1. Receive 0x6363 packets
2. Check command type (0x0B for video)
3. Extract data from offset 7
4. Apply decode transformation (encode_index + bit flip)
5. Assemble frame from multiple packets

## Java Integration

### Control Data Generation
**Location**: `LWUartProtolSdk.java`

```java
// Native function generates control packet payload
public native byte[] LWUartProtolGetControlData(
    ControlPara.Uart_Protocol uart_Protocol, 
    LWUartProtolBean lWUartProtolBean
);
```

### Control Parameters
**Location**: `JoystickPara.java`

```java
public class JoystickPara {
    public int throttle;    // Left stick Y
    public int rudder;      // Left stick X
    public int aileron;     // Right stick X
    public int elvator;     // Right stick Y
    public int aileronTrim;
    public int elvatorTrim;
    public int rudderTrim;
    public int ptz_h;       // Pan
    public int ptz_v;       // Tilt
}
```

### Send Loop
**Location**: `FlyCtrl.java` lines 400-420

```java
while (isNeedSendData) {
    updateSendData();  // Populates control parameters
    if (get_sendData != null) {
        LeweiLib.LW93SendUdpData(get_sendData, get_sendData.length);
    }
    Thread.sleep(50);  // Send every 50ms
}
```

## Python Implementation

See `udp_processor.py` for complete implementation that handles both camera types.

### Usage

```bash
# Listen for video stream
python3 udp_processor.py --port 6000

# Custom output directory
python3 udp_processor.py --port 6000 --output my_frames
```

## Key Findings Summary

1. **Two Camera Protocols**: HD (lewei_cmd) and VGA (0x6363)
2. **HD JPEG Offset**: Data starts at byte 32 (0x20) in packet
3. **VGA Data Offset**: Data starts at byte 7 in packet
4. **Control Protocol**: Uses 0x6363 header with joystick values
5. **Frame Assembly**: Multiple packets per frame, last packet is smaller
6. **Send Rate**: Control packets sent every 50ms

## References

- Reversed binary: `liblewei-3.2.2.so.c`
- Java sources: `tools/App/LW FPV_1.9.2/sources/com/lewei/`
- Native libraries: `tools/App/LW FPV_1.9.2/resources/lib/armeabi-v7a/`
