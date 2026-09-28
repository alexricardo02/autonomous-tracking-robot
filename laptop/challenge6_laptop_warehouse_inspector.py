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
# 2. MAIN 360 SCANNER LOGIC
# ==========================================
def main():
    global latest_frame
    
    threading.Thread(target=video_receiver, daemon=True).start()
    connect_command_socket()

    print("\n[AI] Loading YOLOv3 Model (All 80 COCO Classes)...")
    detector = ObjectDetection()
    detector.setModelTypeAsTinyYOLOv3()
    detector.setModelPath("tiny-yolov3.pt")
    detector.loadModel()
    print("[AI] Model Loaded Successfully!")

    # Wait for the first video frame before starting the rotation
    print("[SYSTEM] Waiting for initial camera frame...")
    while latest_frame is None:
        time.sleep(0.1)

    print("\n" + "="*50)
    print("🚀 STARTING 360 DEGREE WAREHOUSE INSPECTION")
    print("="*50)

    # --- SCANNING PARAMETERS ---
    ROTATION_DURATION = 25.0  # Seconds for a full 360° rotation (adjust to floor conditions!)
    ROTATION_SPEED = 1.0      # Constant rotation speed
    COOLDOWN_TIME = 2.5       # Seconds an object must be out of view before being counted again

    inventory = {}            # Stores { "bottle": 2, "chair": 1, ... }
    last_seen_objects = {}    # Stores { "bottle": timestamp, ... }
    
    start_time = time.time()
    scan_active = True

    try:
        while scan_active:
            elapsed_time = time.time() - start_time
            if elapsed_time >= ROTATION_DURATION:
                scan_active = False
                break

            if latest_frame is None:
                time.sleep(0.01)
                continue
                
            frame_to_process = latest_frame.copy()
            current_time = time.time()
            state_trigger = "NONE"

            # Run inference on ALL objects (no custom_objects filter!)
            detections = detector.detectObjectsFromImage(
                input_image=frame_to_process,
                minimum_percentage_probability=50
            )

            # Extract all classes detected in THIS frame (unique set)
            classes_in_frame = set([obj["name"] for obj in detections])

            # --- INVENTORY AND COOLDOWN LOGIC ---
            for class_name in classes_in_frame:
                # If the object is new OR the cooldown has expired (object was temporarily out of view)
                if class_name not in last_seen_objects or (current_time - last_seen_objects[class_name] > COOLDOWN_TIME):
                    inventory[class_name] = inventory.get(class_name, 0) + 1
                    state_trigger = "FOUND"
                    print(f"🎉 [INVENTORY] New object detected: {class_name.upper()} (Total count: {inventory[class_name]})")
                
                # Update the timestamp as long as the object is visible
                last_seen_objects[class_name] = current_time

            # Draw bounding boxes on the video feed
            for obj in detections:
                box = obj["box_points"]
                name = obj["name"]
                percentage = obj["percentage_probability"]
                cv2.rectangle(frame_to_process, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
                cv2.putText(frame_to_process, f"{name} {int(percentage)}%", (box[0], box[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Send command: rotate at constant speed; STATE_TRIGGER signals new finds for audio
            send_command(f"WHEELS:{ROTATION_SPEED},{-ROTATION_SPEED},{state_trigger}")

            # Draw HUD on the live stream
            y_offset = 30
            cv2.putText(frame_to_process, f"SCANNING 360... Progress: {int((elapsed_time/ROTATION_DURATION)*100)}%", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            for key, val in inventory.items():
                y_offset += 20
                cv2.putText(frame_to_process, f"- {key}: {val}", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow("Warehouse AI 360 Scanner", frame_to_process)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[INFO] Scan manually aborted.")
                break

    finally:
        # After time expires or on abort: full stop!
        print("\n" + "="*50)
        print("🏁 INSPECTION COMPLETE! FINAL INVENTORY:")
        print("="*50)
        if not inventory:
            print("No objects detected.")
        for item, count in inventory.items():
            print(f"📦 {item.upper()}: {count}")
        print("="*50)

        send_command("WHEELS:0.0,0.0,NONE")
        if command_socket: command_socket.close()
        cv2.destroyAllWindows()
        print("[INFO] AI Backend Terminated Safely.")

if __name__ == "__main__":
    main()