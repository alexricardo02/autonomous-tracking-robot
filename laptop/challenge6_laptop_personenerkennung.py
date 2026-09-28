import numpy as np
import cv2
import socket
import struct
import pickle
import time
import threading
from imageai.Detection import ObjectDetection

# ==========================================
# 1. NETWORK CONFIGURATION
# ==========================================
PI_IP_ADDRESS = "192.168.137.129"  
VIDEO_PORT = 9999
COMMAND_PORT = 9998

latest_frame = None
command_socket = None

def video_receiver():
    global latest_frame
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    print(f"[NETWORK] Connecting to Video Stream at {PI_IP_ADDRESS}:{VIDEO_PORT}...")
    while True:
        try:
            client_socket.connect((PI_IP_ADDRESS, VIDEO_PORT))
            print("[NETWORK] Video Connection Established!")
            break
        except ConnectionRefusedError:
            time.sleep(1)

    data_buffer = b""
    payload_size = struct.calcsize("Q")

    try:
        while True:
            while len(data_buffer) < payload_size:
                packet = client_socket.recv(4096)
                if not packet: break
                data_buffer += packet
            
            packed_msg_size = data_buffer[:payload_size]
            data_buffer = data_buffer[payload_size:]
            msg_size = struct.unpack("Q", packed_msg_size)[0]

            while len(data_buffer) < msg_size:
                packet = client_socket.recv(4096)
                if not packet: break
                data_buffer += packet
            
            frame_data = data_buffer[:msg_size]
            data_buffer = data_buffer[msg_size:]

            np_arr = np.frombuffer(frame_data, np.uint8)
            latest_frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
    except Exception as e:
        print(f"[ERROR] Video stream disconnected: {e}")
    finally:
        client_socket.close()

def connect_command_socket():
    global command_socket
    command_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"[NETWORK] Connecting to Command Channel at {PI_IP_ADDRESS}:{COMMAND_PORT}...")
    while True:
        try:
            command_socket.connect((PI_IP_ADDRESS, COMMAND_PORT))
            print("[NETWORK] Command Connection Established!")
            break
        except ConnectionRefusedError:
            time.sleep(1)

def send_command(cmd_string):
    global command_socket
    try:
        if command_socket:
            command_socket.sendall(cmd_string.encode('utf-8'))
    except Exception:
        pass

# ==========================================
# 4. MAIN AI & LOGIC LOOP
# ==========================================
def main():
    global latest_frame
    
    threading.Thread(target=video_receiver, daemon=True).start()
    connect_command_socket()

    print("\n[AI] Loading Tiny-YOLOv3 Deep Learning Model...")
    detector = ObjectDetection()
    detector.setModelTypeAsTinyYOLOv3()
    detector.setModelPath("tiny-yolov3.pt")
    detector.loadModel()
    
    custom_objects = detector.CustomObjects(person=True)
    print("[AI] Model Loaded Successfully! Starting Autonomous Tracking.")

    state = "SEARCHING"
    last_seen_time = time.time()
    search_start_time = time.time()
    
    # --- PROPORTIONAL CONTROL PARAMETERS (Same as Challenge 5) ---
    CENTER_X = 200 # The mathematical center of a 400px wide frame
    DEADZONE_X = 45 # Slightly stricter deadzone
    Kp = 0.012 # Proportional constant
    MIN_TURN_SPEED = 0.5
    MAX_TURN_SPEED = 4.0
    
    TARGET_HEIGHT_MIN = 150 
    TARGET_HEIGHT_MAX = 220 

    waiting_print_timer = time.time()

    try:
        while True:
            if latest_frame is None:
                if time.time() - waiting_print_timer > 3.0:
                    print("[WAITING] Connected, but no video received from Pi yet...")
                    waiting_print_timer = time.time()
                time.sleep(0.1)
                continue
                
            frame_to_process = latest_frame.copy()

            detections = detector.detectObjectsFromImage(
                custom_objects=custom_objects,
                input_image=frame_to_process,
                minimum_percentage_probability=60
            )

            best_person = None
            largest_area = 0

            for obj in detections:
                if obj["name"] == "person":
                    box = obj["box_points"]
                    width = box[2] - box[0]
                    height = box[3] - box[1]
                    area = width * height
                    
                    if height > (width * 1.3): 
                        if area > largest_area:
                            largest_area = area
                            best_person = obj

            current_time = time.time()

            if best_person is not None:
                state = "TRACKING"
                last_seen_time = current_time
                
                box = best_person["box_points"]
                p_width = box[2] - box[0]
                p_height = box[3] - box[1]
                p_center_x = box[0] + (p_width // 2)

                cv2.rectangle(frame_to_process, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 3)
                cv2.putText(frame_to_process, "TARGET LOCKED", (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                # --- PROPORTIONAL CONTROL AND MOVEMENT LOGIC ---
                delta_x = p_center_x - CENTER_X
                
                # Calculate dynamic speed based on how far the person is from the center
                dynamic_speed = abs(delta_x) * Kp
                dynamic_speed = max(MIN_TURN_SPEED, min(dynamic_speed, MAX_TURN_SPEED))

                if p_height > TARGET_HEIGHT_MAX:
                    # Person very close: EMERGENCY BRAKE
                    send_command("WHEELS:0.0,0.0")
                    action = "BRAKING (Too Close)"
                    
                elif delta_x < -DEADZONE_X:
                    # Person on the left: Turn left proportionally
                    # Send command like "WHEELS:-2.5,2.5"
                    send_command(f"WHEELS:{-dynamic_speed:.1f},{dynamic_speed:.1f}")
                    action = f"TURNING LEFT (Speed: {dynamic_speed:.1f})"
                    
                elif delta_x > DEADZONE_X:
                    # Person on the right: Turn right proportionally
                    send_command(f"WHEELS:{dynamic_speed:.1f},{-dynamic_speed:.1f}")
                    action = f"TURNING RIGHT (Speed: {dynamic_speed:.1f})"
                    
                elif p_height < TARGET_HEIGHT_MIN:
                    # Centered, but far: ADVANCE
                    send_command("WHEELS:8.0,8.0")
                    action = "ADVANCING"
                    
                else:
                    # Centered and at perfect distance: STOP
                    send_command("WHEELS:0.0,0.0")
                    action = "HOLDING POSITION"

                print(f"[STATE: {state}] H:{p_height}px | Offset:{delta_x}px | Act: {action}")

            else:
                time_lost = current_time - last_seen_time

                if time_lost < 2.0:
                    send_command("WHEELS:0.0,0.0")
                    print(f"[STATE: GRACE PERIOD] Target lost, waiting...")
                else:
                    if state == "TRACKING":
                        state = "SEARCHING"
                        search_start_time = current_time
                    
                    if state == "SEARCHING":
                        time_searching = current_time - search_start_time
                        
                        if time_searching < 15.0:
                            # Smooth search: Slow right turn at speed 3.0
                            send_command("WHEELS:3.0,-3.0")
                            print(f"[STATE: SEARCHING] Sweeping area... ({int(time_searching)}s/15s)")
                        else:
                            state = "IDLE"
                            send_command("WHEELS:0.0,0.0")
                            search_start_time = current_time
                            
                    elif state == "IDLE":
                        time_sleeping = current_time - search_start_time
                        time_left = 600.0 - time_sleeping
                        
                        send_command("WHEELS:0.0,0.0")
                        print(f"[STATE: IDLE] Sleeping. Next scan in {int(time_left)} s.", end="\r")
                        
                        if time_sleeping >= 600.0:
                            state = "SEARCHING"
                            search_start_time = current_time

            cv2.imshow("Robot AI Backend - Companion Bot", frame_to_process)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n[INFO] User interrupted the program.")
    finally:
        send_command("WHEELS:0.0,0.0")
        if command_socket: command_socket.close()
        cv2.destroyAllWindows()
        print("[INFO] AI Backend Terminated Safely.")

if __name__ == "__main__":
    main()