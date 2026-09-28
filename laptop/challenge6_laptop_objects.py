import cv2
import socket
import struct
import time
import threading
import numpy as np
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
    
    while True:
        try:
            client_socket.connect((PI_IP_ADDRESS, VIDEO_PORT))
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
    while True:
        try:
            command_socket.connect((PI_IP_ADDRESS, COMMAND_PORT))
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
# 2. USER INTERFACE (TERMINAL MENU)
# ==========================================
def get_target_from_user():
    print("\n" + "="*50)
    print("   TARGET HUNTER AI - AVAILABLE OBJECTS")
    print("="*50)
    print("PEOPLE & ANIMALS: person, bird, cat, dog, horse, cow")
    print("VEHICLES:         bicycle, car, motorcycle, bus, train")
    print("CLASSROOM:        backpack, umbrella, handbag, book, clock")
    print("ELECTRONICS:      laptop, mouse, keyboard, cell phone, tv")
    print("FOOD & DRINK:     bottle, cup, apple, banana, sandwich")
    print("FURNITURE:        chair, couch, bed, dining table, vase")
    print("="*50)
    
    target = input("\n[INPUT] Type the name of the object you want to hunt: ").strip().lower()
    if target == "":
        target = "person" # Default fallback
    print(f"\n[INFO] Target acquired. The robot will now hunt for: '{target.upper()}'")
    return target

# ==========================================
# 3. MAIN AI & LOGIC LOOP
# ==========================================
def main():
    global latest_frame
    
    # 1. Ask user for the target
    target_object = get_target_from_user()
    
    # 2. Start Network
    print(f"[NETWORK] Connecting to Pi at {PI_IP_ADDRESS}...")
    threading.Thread(target=video_receiver, daemon=True).start()
    connect_command_socket()

    # 3. Start AI
    print("[AI] Loading Tiny-YOLOv3 Deep Learning Model...")
    detector = ObjectDetection()
    detector.setModelTypeAsTinyYOLOv3()
    detector.setModelPath("tiny-yolov3.pt") 
    detector.loadModel()
    print("[AI] Model Loaded Successfully! Starting Autonomous Tracking.")

    state = "SEARCHING"
    last_seen_time = time.time()
    search_start_time = time.time()
    
    # --- NEW: Variable to prevent sound spamming ---
    target_locked = False 
    
    # --- TUNED PROPORTIONAL CONTROL PARAMETERS ---
    CENTER_X = 200        
    DEADZONE_X = 45       
    Kp = 0.012            
    MIN_TURN_SPEED = 0.5  
    MAX_TURN_SPEED = 3.0  
    
    # Target heights for distancing
    TARGET_HEIGHT_MAX = 200 # If the bounding box is taller than this, the robot stops (reached)

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
                input_image=frame_to_process,
                minimum_percentage_probability=50
            )

            best_target = None
            largest_area = 0

            # Find the largest instance of the requested object
            for obj in detections:
                if obj["name"] == target_object:
                    box = obj["box_points"]
                    width = box[2] - box[0]
                    height = box[3] - box[1]
                    area = width * height
                    
                    if area > largest_area:
                        largest_area = area
                        best_target = obj

            current_time = time.time()

            if best_target is not None:
                state = "TRACKING"
                last_seen_time = current_time
                
                # --- SINGLE SOUND LOGIC ---
                # Only send "FOUND" once per discovery. Otherwise, just send "TRACKING".
                if not target_locked:
                    status_flag = "FOUND"
                    target_locked = True
                else:
                    status_flag = "TRACKING"
                
                box = best_target["box_points"]
                p_width = box[2] - box[0]
                p_height = box[3] - box[1]
                p_center_x = box[0] + (p_width // 2)

                # Draw bounding box
                cv2.rectangle(frame_to_process, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 3)
                cv2.putText(frame_to_process, f"TARGET: {target_object.upper()}", (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                # --- PROPORTIONAL CONTROL LOGIC ---
                delta_x = p_center_x - CENTER_X
                dynamic_speed = abs(delta_x) * Kp
                dynamic_speed = max(MIN_TURN_SPEED, min(dynamic_speed, MAX_TURN_SPEED))

                action = ""
                
                # --- CENTRALIZATION AND ADVANCE (Like Challenge 5) ---
                if p_height > TARGET_HEIGHT_MAX:
                    # Target is too close, brake!
                    send_command(f"WHEELS:0.0,0.0,{status_flag}")
                    action = "BRAKING (Reached Target)"
                    
                elif delta_x < -DEADZONE_X:
                    # Target is off to the left, center it
                    send_command(f"WHEELS:{-dynamic_speed:.1f},{dynamic_speed:.1f},{status_flag}")
                    action = f"TURNING LEFT (Speed: {dynamic_speed:.1f})"
                    
                elif delta_x > DEADZONE_X:
                    # Target is off to the right, center it
                    send_command(f"WHEELS:{dynamic_speed:.1f},{-dynamic_speed:.1f},{status_flag}")
                    action = f"TURNING RIGHT (Speed: {dynamic_speed:.1f})"
                    
                else:
                    # Target is perfectly centered AND not too close -> MOVE FORWARD!
                    send_command(f"WHEELS:7.0,7.0,{status_flag}")
                    action = "CENTERED -> ADVANCING TO TARGET"

                print(f"[STATE: {state} | T: {target_object.upper()}] Offset:{delta_x}px | Act: {action}")

            else:
                time_lost = current_time - last_seen_time

                if time_lost < 2.0:
                    # Grace period (Ignore temporary AI flickering)
                    send_command("WHEELS:0.0,0.0,NONE")
                    print(f"[STATE: GRACE PERIOD] Target lost, waiting...")
                else:
                    # Target is officially lost. Reset the sound lock so it can beep again later.
                    target_locked = False 
                    
                    if state == "TRACKING":
                        state = "SEARCHING"
                        search_start_time = current_time
                    
                    if state == "SEARCHING":
                        time_searching = current_time - search_start_time
                        
                        if time_searching < 15.0:
                            send_command("WHEELS:2.0,-2.0,NONE")
                            print(f"[STATE: SEARCHING] Sweeping area... ({int(time_searching)}s/15s)")
                        else:
                            state = "IDLE"
                            send_command("WHEELS:0.0,0.0,NONE")
                            search_start_time = current_time
                            
                    elif state == "IDLE":
                        time_sleeping = current_time - search_start_time
                        time_left = 600.0 - time_sleeping
                        
                        send_command("WHEELS:0.0,0.0,NONE")
                        print(f"[STATE: IDLE] Sleeping. Next scan in {int(time_left)} s.", end="\r")
                        
                        if time_sleeping >= 600.0:
                            state = "SEARCHING"
                            search_start_time = current_time

            cv2.imshow("Robot AI Backend - Selective Target Hunter", frame_to_process)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n[INFO] User interrupted the program.")
    finally:
        send_command("WHEELS:0.0,0.0,NONE")
        if command_socket: command_socket.close()
        cv2.destroyAllWindows()
        print("[INFO] AI Backend Terminated Safely.")

if __name__ == "__main__":
    main()