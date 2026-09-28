import cv2
import numpy as np
import asyncio
import subprocess
import time
import threading
import socket     
import pickle     
import struct     

from irobot_edu_sdk.backend.bluetooth import Bluetooth
from irobot_edu_sdk.robots import Create3, event

# ==========================================
# 0. GLOBAL VARIABLES (DECOUPLED ARCHITECTURE)
# ==========================================
shared_frame = None            # Pure and real-time frame from the camera
current_command = "STOP"       # Current instruction received from the Laptop

# ==========================================
# 1. THREAD 1: CAMERA READER (ZERO TCP LATENCY)
# ==========================================
def camera_reader_thread():
    global shared_frame
    cap = cv2.VideoCapture("tcp://127.0.0.1:8888")
    
    while True:
        ret, frame = cap.read()
        if ret:
            # BANDWIDTH OPTIMIZATION: 
            # Pickling a huge uncompressed image will saturate the Hotspot WiFi.
            # Downscaling to 400x300 ensures extreme fluidity for the AI model.
            shared_frame = cv2.resize(frame, (400, 300))
        else:
            time.sleep(0.01)

threading.Thread(target=camera_reader_thread, daemon=True).start()

# ==========================================
# 2. THREAD 2: VIDEO STREAMING SERVER (PORT 9999)
# ==========================================
def video_streaming_server():
    global shared_frame
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # 0.0.0.0 allows connections from any IP (your laptop on the hotspot)
    server_socket.bind(('0.0.0.0', 9999)) 
    server_socket.listen(5)
    
    print("[INFO] VIDEO SERVER started. Waiting for connection on port 9999...")

    while True:
        client_socket, addr = server_socket.accept()
        print(f"[INFO] Laptop (Video) connected from: {addr}")
        try:
            while True:
                if shared_frame is not None:
                    # Copy the frame to prevent memory corruption during encoding
                    frame_to_send = shared_frame.copy() 
                    
                    # 1. Serialize the frame (Convert to Bytes)
                    ret, buffer = cv2.imencode('.jpg', frame_to_send, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if not ret: continue
                    serialized_frame = buffer.tobytes()
                    
                    # 2. Pack the exact size ("Q" = 8 bytes universally for 64-bit sync)
                    message_size = struct.pack("Q", len(serialized_frame))
                    
                    # 3. Send size + frame over the network
                    client_socket.sendall(message_size + serialized_frame)
                    
                    # Limit to ~20 FPS to avoid saturating the router/hotspot buffer
                    time.sleep(0.03) 
        except Exception as e:
            print(f"[WARNING] Video connection dropped: {e}")
            client_socket.close()

threading.Thread(target=video_streaming_server, daemon=True).start()

# ==========================================
# 3. THREAD 3: COMMAND RECEIVER SERVER (PORT 9998)
# ==========================================
def command_receiver_server():
    global current_command
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', 9998))
    server_socket.listen(5)
    
    print("[INFO] COMMAND SERVER started. Waiting for connection on port 9998...")

    while True:
        client_socket, addr = server_socket.accept()
        print(f"[INFO] Laptop (Control) connected from: {addr}")
        try:
            while True:
                # Receive up to 1024 bytes (our commands will be very short)
                data = client_socket.recv(1024)
                if not data:
                    break
                
                # Decode bytes to text and strip whitespaces
                current_command = data.decode('utf-8').strip()
                # print(f"[COMMAND RECEIVED] -> {current_command}") # Optional: Uncomment for debugging
                
        except Exception as e:
            print(f"[WARNING] Control connection dropped: {e}")
            client_socket.close()
            current_command = "STOP" # Emergency brake on disconnect

threading.Thread(target=command_receiver_server, daemon=True).start()

# ==========================================
# 1. AUTOMATIC AND SEQUENTIAL BLUETOOTH MANAGEMENT
# ==========================================
print("[INFO] 1/4 - Cleaning the Bluetooth cache...")
subprocess.run(['bluetoothctl', 'scan', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

print("[INFO] 2/4 - Scanning for the robot (3 seconds)...")
ble_scan_process = subprocess.Popen(['bluetoothctl', 'scan', 'on'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3) 

print("[INFO] 3/4 - Stopping scan to prevent connection crashes...")
ble_scan_process.terminate()
subprocess.run(['bluetoothctl', 'scan', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1) 

print("[INFO] 4/4 - Connecting SDK...")
backend = Bluetooth()
robot = Create3(backend)

# ==========================================
# 5. MAIN LOOP (BLIND EXECUTION)
# ==========================================
@event(robot.when_play)
async def main_loop(robot):
    global current_command
    
    print("[INFO] Robot ready! Waiting for Laptop AI to send kinematic vectors...")

    try:
        while True:
            # El nuevo protocolo espera comandos así: "WHEELS:izq,der" (Ej: "WHEELS:-3.2,3.2")
            if current_command.startswith("WHEELS:"):
                try:
                    # Extraer los números del texto
                    # 1. Quita "WHEELS:" -> "-3.2,3.2"
                    # 2. Separa por la coma -> ["-3.2", "3.2"]
                    speeds_str = current_command.split(":")[1].split(",")
                    left_speed = float(speeds_str[0])
                    right_speed = float(speeds_str[1])
                    
                    await robot.set_wheel_speeds(left_speed, right_speed)
                except Exception as e:
                    # Si hay un error decodificando, frena por seguridad
                    await robot.set_wheel_speeds(0, 0)
            else:
                # Fallback de seguridad si el comando está vacío o corrupto
                await robot.set_wheel_speeds(0, 0)
                
            await asyncio.sleep(0.05) 

    except KeyboardInterrupt:
        print("\n[INFO] Manual shutdown triggered.")
    finally:
        await robot.set_wheel_speeds(0, 0)
        print("[INFO] All systems safely terminated.")

robot.play()
