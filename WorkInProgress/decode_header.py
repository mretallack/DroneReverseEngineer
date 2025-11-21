#!/usr/bin/env python3
"""
Decode 0x6363 packet header based on liblewei-3.2.2.so.c structure
Stack layout from line 15240-15266
"""

import struct

def decode_vga_header(hex_str):
    """Decode VGA packet header (0x6363 protocol)"""
    data = bytes.fromhex(hex_str)
    
    print(f"Raw hex: {hex_str}")
    print(f"Length: {len(data)} bytes\n")
    
    # Stack layout from C code (line 15240-15266)
    # local_7d8 (offset 0x00): 0x6363 header (2 bytes, short)
    # local_7d6 (offset 0x02): Command type (1 byte, char)
    # local_7d5 (offset 0x03): Sequence/packet ID (2 bytes, short)
    # local_7d3 (offset 0x05): Packet length (2 bytes, ushort)
    # local_7d1 (offset 0x07): Frame type/flags (1 byte, byte)
    # uStack_7d0 (offset 0x08): Frame ID (4 bytes, uint)
    # local_7cc (offset 0x0C): Metadata (4 bytes, uint)
    # ... more metadata fields ...
    
    if len(data) < 12:
        print("Error: Packet too short")
        return
    
    # Parse header
    header = struct.unpack('<H', data[0:2])[0]
    cmd_type = data[2]
    seq_id = struct.unpack('<H', data[3:5])[0]
    pkt_len = struct.unpack('<H', data[5:7])[0]
    frame_type = data[7]
    frame_id = struct.unpack('<I', data[8:12])[0] if len(data) >= 12 else 0
    
    print(f"Header:       0x{header:04X} ({'VGA' if header == 0x6363 else 'Unknown'})")
    print(f"Command Type: 0x{cmd_type:02X} ({get_cmd_name(cmd_type)})")
    print(f"Sequence ID:  0x{seq_id:04X} ({seq_id})")
    print(f"Packet Len:   0x{pkt_len:04X} ({pkt_len} bytes)")
    print(f"Frame Type:   0x{frame_type:02X}")
    print(f"Frame ID:     0x{frame_id:08X} ({frame_id})")
    
    # Parse payload (offset 0x0C onwards)
    if len(data) > 12:
        print(f"\nPayload ({len(data)-12} bytes):")
        payload = data[12:]
        
        # Try to decode as ASCII string
        try:
            text = payload.rstrip(b'\x00').decode('ascii')
            if text.isprintable():
                print(f"  ASCII: '{text}'")
        except:
            pass
        
        # Show hex dump
        print(f"  Hex: {payload.hex()}")

def get_cmd_name(cmd_type):
    """Get command type name from C code"""
    # From line 15296-15472
    cmd_names = {
        0x01: "Heartbeat",
        0x03: "Multi-packet Video",
        0x04: "WiFi SSID (Set)",
        0x06: "WiFi SSID (Get)",
        0x07: "WiFi Password (Set)",
        0x09: "Key Event",
        0x0B: "Single Video Data",
        0x0C: "Clear WiFi",
        0x0D: "WiFi Password (Get)",
        0x0F: "Camera LED On",
        0x10: "Camera LED Off"
    }
    return cmd_names.get(cmd_type, f"Unknown (0x{cmd_type:02X})")

if __name__ == '__main__':
    # Decode the provided header
    header_hex = "63630100006300484153414b45452d576946692d31393134354300000000000000000000000000000000000000000000000000000000"
    decode_vga_header(header_hex)
