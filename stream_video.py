import socket
import time
import sys
import cv2
import numpy as np

# --- CONSTANTS (Defined outside for use in both functions) ---
DRONE_IP = "192.168.0.1"
DRONE_COMMAND_PORT = 40000
LOCAL_SOURCE_PORT = 54321
START_COMMAND = bytes.fromhex("63630100000000") 
PROPRIETARY_HEADER_LENGTH = 54
JPEG_SOI = bytes.fromhex("FFD8")
JPEG_EOI = bytes.fromhex("FFD9")
JPEG_SOS = bytes.fromhex("FFDA")
SOS_PARAM_LENGTH = 12 # SOS marker (FF DA) is followed by 12 bytes of parameters

# Path to save the raw video data
OUTPUT_FILE = "drone_raw_video_stream.bin" 

# --- FUNCTIONS ---

def encode_index(frame_id, data_length):
    """
    Calculate obfuscation index (from liblewei-3.2.2.so line 8718)
    """
    if data_length == 0:
        return 0
    if (data_length & 1) == 0:  # Even
        val = data_length + 1 + (data_length ^ frame_id) ^ data_length
        return val % data_length
    else:  # Odd
        val = (data_length ^ frame_id) + data_length ^ data_length
        return val % data_length

def decode_vga_obfuscation(data, frame_id, frame_type):
    """
    Decode VGA data obfuscation (from liblewei-3.2.2.so line 15325-15327)
    Only applies if frame_type != 0x02
    """
    if frame_type == 0x02 or len(data) == 0:
        return data
    
    data = bytearray(data)
    index = encode_index(frame_id, len(data))
    if 0 <= index < len(data):
        data[index] = (~data[index]) & 0xFF
        print(f"Decoded obfuscation at index {index}")
    return bytes(data)

def decode_packet_header(data):
    """
    Decode 0x6363 packet header (from liblewei-3.2.2.so line 15240-15266)
    Returns dict with parsed fields
    """
    import struct
    
    if len(data) < 12:
        return None
    
    header = struct.unpack('<H', data[0:2])[0]
    if header != 0x6363:
        return None
    
    # print the header
    print(f"Header: {data[0:60].hex()}")

    return {
        'header': header,
        'cmd_type': data[2],
        'seq_id': struct.unpack('<H', data[3:5])[0],
        'pkt_len': struct.unpack('<H', data[5:7])[0],
        'frame_type': data[7],
        'frame_id': struct.unpack('<I', data[8:12])[0],
        'payload': data[12:]
    }

def send_command(sock, drone_ip, drone_port, command):
    """Send command to drone"""
    try:
        sock.sendto(command, (drone_ip, drone_port))
    except socket.error as e:
        print(f"❌ Error sending command: {e}")

import numpy as np

def fix_jpeg_stuffing(jpeg_buffer):
    """
    Corrects the missing 0xFF, 0x00 byte stuffing in a JPEG stream
    that caused the "premature end of data segment" corruption.
    
    Args:
        jpeg_buffer: The assembled frame data (list of ints or bytes).
        
    Returns:
        bytes: The corrected JPEG stream with stuffing inserted.
    """
    # 1. Ensure buffer is bytes for easy searching
    if isinstance(jpeg_buffer, list):
        jpeg_buffer = bytes(jpeg_buffer)

    # 2. Find the Start of Scan (SOS) marker (0xFF DA)
    sos_index = jpeg_buffer.find(b'\xff\xda')
    
    if sos_index == -1:
        print("Error: SOS marker (FF DA) not found.")
        return jpeg_buffer

    # 3. Calculate the index where the *compressed stream* actually starts.
    # SOS length is at sos_index + 2 (2 bytes, Big Endian)
    sos_length_bytes = jpeg_buffer[sos_index + 2 : sos_index + 4]
    sos_length = int.from_bytes(sos_length_bytes, 'big')

    # The compressed stream starts after FF DA, the 2-byte length, and the (Length - 2) bytes of header data.
    stream_start_index = sos_index + 2 + sos_length 

    # 4. Initialize the fixed frame with the entire header (which is already correct)
    fixed_frame = list(jpeg_buffer[:stream_start_index])
    
    # 5. Scan and Fix the compressed data stream
    i = stream_start_index
    stream_end = len(jpeg_buffer) - 2 # Stop two bytes before the final FF D9
    
    while i < stream_end:
        byte = jpeg_buffer[i]
        
        # Append current byte first
        fixed_frame.append(byte)
        
        # Check for illegal 0xFF byte
        if byte == 0xFF:
            next_byte = jpeg_buffer[i+1]
            
            # The critical check: If 0xFF is NOT followed by 0x00 AND 
            # the next byte is NOT a valid marker (valid markers are >= 0xD0, except a few)
            # We assume anything < 0xD0 (0x2D in your case) is the corruption point.
            if next_byte != 0x00 and next_byte < 0xD0:
                # Insert the missing 0x00 stuffing byte
                fixed_frame.append(0x00)
                # Note: We don't advance 'i' here, so the next iteration correctly processes 'next_byte'
                
        i += 1
    
    # 6. Append the final 0xFF D9 (End of Image) markers.
    # The loop stopped 2 bytes early to prevent stuffing the final 0xFF
    fixed_frame.append(jpeg_buffer[-2]) # 0xFF
    fixed_frame.append(jpeg_buffer[-1]) # 0xD9
    
    return bytes(fixed_frame)

import numpy as np

import numpy as np

def repair_and_truncate_frame_final_v7(assembled_buffer):
    """
    1. Modifies the JPEG header to set height to 48 pixels (480 -> 48).
    2. Cuts the data stream to 10% of its original length to remove systematic corruption.
    """
    buffer_bytes = bytes(assembled_buffer)
    
    # --- Part A: Modify Header (Change 480 to 48) ---
    sof0_marker_index = buffer_bytes.find(b'\xff\xc0')
    if sof0_marker_index == -1: return buffer_bytes
    height_offset = sof0_marker_index + 5 
    
    # New Height: 48 (0x0030)
    NEW_HEIGHT_BYTES = b'\x00\x30' 
    modified_header = (
        buffer_bytes[:height_offset] + 
        NEW_HEIGHT_BYTES +
        buffer_bytes[height_offset + 2:]
    )
    
    # --- Part B: Truncate Corrupt Compressed Data ---
    
    sos_index = modified_header.find(b'\xff\xda')
    eoi_index = modified_header.find(b'\xff\xd9')
    if sos_index == -1 or eoi_index == -1: return modified_header

    sos_length = int.from_bytes(modified_header[sos_index + 2 : sos_index + 4], 'big')
    stream_start_index = sos_index + 2 + sos_length 

    compressed_data_length = eoi_index - stream_start_index
    
    # **MINIMUM VIABLE IMAGE**: Keep only 10% of the compressed data
    TRUNCATION_FACTOR = 0.10 
    new_compressed_length = int(compressed_data_length * TRUNCATION_FACTOR)
    
    # Build the final, truncated JPEG file
    final_jpeg = (
        modified_header[:stream_start_index] +  
        modified_header[stream_start_index : stream_start_index + new_compressed_length] + 
        b'\xff\xd9' # Clean EOI marker
    )
    
    print(f"Frame Repaired: Height changed 480->48. Data truncated from {compressed_data_length} to {new_compressed_length} bytes (Factor: {TRUNCATION_FACTOR}).")
    return final_jpeg

def adjust_height_to_29_mcus(jpeg_data):
    """Adjust JPEG height from 480 to 464 pixels (29 MCU rows) to match drone data."""
    data = bytearray(jpeg_data)
    sof_idx = data.find(b'\xff\xc0')
    if sof_idx != -1:
        data[sof_idx + 5] = 0x01  # 464 = 0x01D0
        data[sof_idx + 6] = 0xD0
    return bytes(data)

# Global to store previous frame for blending
_previous_frame = None

def decode_frame(jpeg_data, frame_num):
    """
    Decode a JPEG frame using OpenCV and display it.
    Blends with previous frame if corruption detected.
    """
    global _previous_frame
    
    try:
        #jpeg_data = adjust_height_to_29_mcus(jpeg_data)
        nparr = np.frombuffer(jpeg_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is not None and img.size > 0:
            # If image is shorter than expected (464 vs 480), pad bottom with previous frame
            if img.shape[0] < 480 and _previous_frame is not None:
                # Create full-size image
                full_img = np.zeros((480, 640, 3), dtype=np.uint8)
                full_img[:img.shape[0], :] = img  # Copy decoded part
                full_img[img.shape[0]:, :] = _previous_frame[img.shape[0]:, :]  # Fill bottom from previous
                img = full_img
            
            _previous_frame = img.copy()  # Store for next frame
            cv2.imshow('Drone Video Stream', img)
            cv2.imwrite(f"frames/frame_{frame_num}.jpg", img)
            cv2.waitKey(1)
        else:
            sys.stdout.write(f"\r⚠️ Frame {frame_num} decode failed")
            sys.stdout.flush()

    except Exception as e:
        sys.stdout.write(f"\r❌ Error: {e}")
        sys.stdout.flush()

def stream_manager(drone_ip, drone_port, local_port, command, filename):
    """
    Manages both command sending and stream reception using a single socket 
    bound to a specific local port, and processes MJPEG frames.
    """
    print(f"🔗 Binding local socket to port {local_port}...")
    
    # 1. Create and bind the socket to the specific local port
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', local_port)) 
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
    except socket.error as e:
        print(f"❌ Error binding socket to port {local_port}: {e}")
        print("Note: Port is likely in use. Try changing LOCAL_SOURCE_PORT.")
        return

    # 2. Send initial command
    print(f"📡 Sending initial command...")
    send_command(sock, drone_ip, drone_port, command)
    time.sleep(1)

    # 3. Listen for the video stream
    print(f"\n📺 Starting video listener on port {local_port}...")
    print(f"Listening for video data and decoding frames...")
    print("Press Ctrl+C to stop the listener.")
    
    bytes_received = 0
    start_time = time.time()
    last_command_time = time.time()
    frame_count = 0
    keyframe_data = b'' # This is the reusable JPEG header template

    running_frame=None
    current_frame_sequence=None

    with open(filename, 'wb') as f:
        while True:
            try:
                # Send heartbeat command every 1 second (line 15003)
                current_time = time.time()
                if current_time - last_command_time >= 1.0:
                    send_command(sock, drone_ip, drone_port, command)
                    last_command_time = current_time
                
                data, address = sock.recvfrom(2048)
                f.write(data)
                bytes_received += len(data)
                
                # Process each UDP packet individually
                if len(data) > PROPRIETARY_HEADER_LENGTH and data[:2] == b'\x63\x63':
                    
                    # Decode packet header
                    hdr = decode_packet_header(data)
                    if not hdr:
                        print(f"❌ Invalid packet header")
                        continue
                    
                    message_type = hdr['cmd_type']
                    frame_sequence = hdr['frame_id']
                    sequence_id = data[48] if len(data) > 48 else 0
                    
                    print(f"cmd={message_type:02X} frame={frame_sequence} seq={sequence_id}")

                    if message_type == 0x01:
                        # Heartbeat/ACK
                        try:
                            payload_text = hdr['payload'].rstrip(b'\x00').decode('ascii')
                            print(f"📦 Heartbeat: {payload_text}")
                        except:
                            print("📦 Heartbeat received")

                    # test for type 3, video frame
                    elif message_type == 0x03:
                    
                        # test for new frame
                        if current_frame_sequence!=frame_sequence:
                            # ok, we have a new frame
                            if running_frame:
                                # Apply VGA obfuscation decode if needed
                                frame_type_flag = data[7]  # offset 7 is frame type
                                running_frame = decode_vga_obfuscation(running_frame, current_frame_sequence, frame_type_flag)
                                
                                print(f"Frame size {len(running_frame)}")
                                decode_frame(running_frame, frame_count)

                                # increment the frame count
                                frame_count += 1

                                # reset the running frame
                                running_frame = None

                        current_frame_sequence=frame_sequence

                        payload = data[PROPRIETARY_HEADER_LENGTH:]

                        # print the start of payload
                        #print(f"🔍 Payload starts with: {payload.hex()}")
                        
                        # --- I-Frame (keyframe) Logic: Contains JPEG SOI (FFD8) ---
                        if sequence_id==1 and payload.startswith(JPEG_SOI):

                            #print("JPEG_SOI detected")
                            
                            # set running_frame to payload, new frame
                            running_frame = payload
                        
                            #if frame_count>2:
                            #    sys.exit(0)

                        
                        elif sequence_id>1:
                            print("Append to frame")
                            # append the payload to the running frame
                            running_frame += payload
                        else:
                            # dump frame 200 bytes
                            print(f"❌ I-Frame does not start with JPEG SOI. Dumping 200 bytes: {data[:200].hex()}")
                            raise Exception(f"I-Frame does not start with JPEG SOI") 

                    else:
                        print(f"Unknown message type {message_type}") 
                        raise Exception(f"Unknown message type {message_type}") 
                else:
                    print(f"❌ Packet does not start with proprietary header. Dumping 200 bytes: {data[:200].hex()}")
                    # throw exception we want to see this
                    raise Exception("Packet does not start with proprietary header")
                
                # Print status update
                if bytes_received % (1024 * 100) < 2048: 
                    elapsed = time.time() - start_time
                    rate = (bytes_received / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                    sys.stdout.write(f"\rBytes: {bytes_received / (1024*1024):.2f} MB @ {rate:.2f} MB/s | Frames: {frame_count}")
                    sys.stdout.flush()

            except KeyboardInterrupt:
                break

    print("\n🛑 Listener stopped.")
    print(f"Total data saved: {bytes_received / (1024*1024):.2f} MB")
    print(f"Total frames processed: {frame_count}")
    sock.close()


# --- MAIN EXECUTION ---
if __name__ == '__main__':
    try:
        cv2.namedWindow('Drone Video Stream', cv2.WINDOW_AUTOSIZE)
        stream_manager(DRONE_IP, DRONE_COMMAND_PORT, LOCAL_SOURCE_PORT, START_COMMAND, OUTPUT_FILE)
    finally:
        cv2.destroyAllWindows()