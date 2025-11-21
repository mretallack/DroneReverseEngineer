#!/usr/bin/env python3
"""
Decode VGA packet based on liblewei-3.2.2.so.c structure
"""

import struct

def decode_vga_packet(hex_str):
    """Decode VGA packet (0x6363 protocol) from line 15240-15300"""
    data = bytes.fromhex(hex_str)
    
    print(f"Packet length: {len(data)} bytes")
    print(f"Raw hex: {hex_str}\n")
    
    # Basic header (line 15240-15266)
    header = struct.unpack('<H', data[0:2])[0]
    cmd_type = data[2]
    seq_id = struct.unpack('<H', data[3:5])[0]
    pkt_len = struct.unpack('<H', data[5:7])[0]
    frame_type = data[7]
    frame_id = struct.unpack('<I', data[8:12])[0]
    
    print(f"=== Basic Header ===")
    print(f"Header:       0x{header:04X} ({'VGA' if header == 0x6363 else 'Unknown'})")
    print(f"Command Type: 0x{cmd_type:02X} ({get_cmd_name(cmd_type)})")
    print(f"Sequence ID:  0x{seq_id:04X} ({seq_id})")
    print(f"Packet Len:   0x{pkt_len:04X} ({pkt_len} bytes)")
    print(f"Frame Type:   0x{frame_type:02X}")
    print(f"Frame ID:     0x{frame_id:08X} ({frame_id})")
    
    # Multi-packet video fields (line 15296-15300)
    if cmd_type == 0x03 and len(data) >= 0x2D:
        print(f"\n=== Multi-Packet Video Fields (cmd_type=0x03) ===")
        
        # From C code line 15298-15299
        # uVar36 = (uint)local_7a8;  // packet sequence
        # uVar18 = local_7a6;         // total packets
        # __n = (ulong)local_7a4;     // data length
        
        packet_seq = struct.unpack('<H', data[0x27:0x29])[0]      # local_7a8
        total_packets = struct.unpack('<H', data[0x29:0x2B])[0]   # local_7a6
        data_len = struct.unpack('<H', data[0x2B:0x2D])[0]        # local_7a4
        
        print(f"Packet Seq:    {packet_seq}/{total_packets}")
        print(f"Data Length:   {data_len} bytes")
        
        # JPEG data starts at offset 0x36 (54 bytes) - line 15304
        jpeg_offset = 0x36
        if len(data) > jpeg_offset:
            jpeg_data = data[jpeg_offset:]
            print(f"\nJPEG Data Offset: 0x{jpeg_offset:02X} ({jpeg_offset} bytes)")
            print(f"JPEG Data Length: {len(jpeg_data)} bytes")
            
            if len(jpeg_data) >= 4:
                print(f"JPEG Start: {jpeg_data[:4].hex()}")
                if jpeg_data[:2] == b'\xFF\xD8':
                    print("  ✓ Valid JPEG SOI marker (0xFFD8)")
                else:
                    print("  ✗ No JPEG SOI marker")
    
    # Show metadata section (offsets 0x0C to 0x35)
    if len(data) >= 0x36:
        print(f"\n=== Metadata (offsets 0x0C-0x35) ===")
        metadata = data[0x0C:0x36]
        print(f"Hex: {metadata.hex()}")
        
        # Try to decode specific fields if known
        if len(data) >= 0x2D:
            print(f"\nKnown fields:")
            print(f"  Offset 0x27-0x28: {struct.unpack('<H', data[0x27:0x29])[0]:04X} (packet_seq)")
            print(f"  Offset 0x29-0x2A: {struct.unpack('<H', data[0x29:0x2B])[0]:04X} (total_packets)")
            print(f"  Offset 0x2B-0x2C: {struct.unpack('<H', data[0x2B:0x2D])[0]:04X} (data_len)")

def get_cmd_name(cmd_type):
    """Get command type name from C code line 15296-15472"""
    cmd_names = {
        0x01: "Heartbeat",
        0x03: "Multi-packet Video",
        0x09: "Key Event",
        0x0B: "Single Video Data"
    }
    return cmd_names.get(cmd_type, f"Unknown")

if __name__ == '__main__':
    # Decode the provided packet
    packet_hex = "63630300004601037e675a5a681c00005a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a01060006001001a28a0028a28a"
    decode_vga_packet(packet_hex)
