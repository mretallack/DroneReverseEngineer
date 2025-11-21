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

# Global to store previous frame for blending
_previous_frame = None

def decode_frame(jpeg_data, frame_num):
    """
    Decode a JPEG frame using OpenCV and display it.
    Blends with previous frame if corruption detected.
    """
    global _previous_frame
    
    try:
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