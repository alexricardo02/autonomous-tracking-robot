import cv2
import numpy as np
import asyncio
import subprocess
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from irobot_edu_sdk.backend.bluetooth import Bluetooth
from irobot_edu_sdk.robots import Create3, event

# ==========================================
# 0. GLOBAL VARIABLES AND MULTITHREADING (ZERO LAG)
# ==========================================
latest_frame = None  # Frame for the web server (with overlays/drawings)
shared_frame = None  # Pure and real-time frame from the camera

# THREAD 1: Camera Reader at max speed (Eliminates 100% of TCP latency)
def camera_reader_thread():
    global shared_frame
    cap = cv2.VideoCapture("tcp://127.0.0.1:8888")
    while True:
        ret, frame = cap.read()
        if ret:
            shared_frame = frame
        else:
            time.sleep(0.01)

threading.Thread(target=camera_reader_thread, daemon=True).start()

# THREAD 2: Native Web Server (Live HD Video)
class LiveStreamingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        global latest_frame
        if self.path == '/' or self.path == '':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            html = '<h1>Robot Vision Live HD</h1><img src="/video_feed" width="600">'
            self.wfile.write(html.encode('utf-8'))
        
        elif self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    if latest_frame is not None:
                        # QUALITY IMPROVEMENT: Force JPEG compression to 85% for maximum sharpness
                        ret, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        if ret:
                            frame_bytes = buffer.tobytes()
                            self.wfile.write(b'--frame\r\n')
                            self.wfile.write(b'Content-Type: image/jpeg\r\n')
                            self.wfile.write(f'Content-Length: {len(frame_bytes)}\r\n\r\n'.encode())
                            self.wfile.write(frame_bytes)
                            self.wfile.write(b'\r\n')
                    time.sleep(0.04) # 25 FPS for the browser
            except Exception:
                pass

def start_native_server():
    server = HTTPServer(('0.0.0.0', 5000), LiveStreamingHandler)
    server.serve_forever()

threading.Thread(target=start_native_server, daemon=True).start()

# ==========================================
# 1. AUTOMATIC AND SEQUENTIAL BLUETOOTH MANAGEMENT
# ==========================================
print("[INFO] 1/4 - Cleaning the Bluetooth chip...")
subprocess.run(['bluetoothctl', 'scan', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

print("[INFO] 2/4 - Scanning the air (3 seconds) to find the robot...")
ble_scan_process = subprocess.Popen(['bluetoothctl', 'scan', 'on'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3) 

print("[INFO] 3/4 - Stopping the scan to prevent connection crashes...")
ble_scan_process.terminate()
subprocess.run(['bluetoothctl', 'scan', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1) 

# ==========================================
# 2. INITIALIZE SDK AND STRICT COLOR FILTERS
# ==========================================
print("[INFO] 4/4 - Initiating connection with the iRobot SDK...")
backend = Bluetooth()
robot = Create3(backend)

lower_blue = np.array([100, 150, 100])
upper_blue = np.array([130, 255, 255])

lower_red1 = np.array([0, 150, 100])
upper_red1 = np.array([10, 255, 255])
lower_red2 = np.array([170, 150, 100])
upper_red2 = np.array([180, 255, 255])

kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

# ==========================================
# 3. MAIN LOOP (SENSOR FUSION)
# ==========================================
@event(robot.when_play)
async def main_loop(robot):
    global latest_frame, shared_frame
    
    print("[INFO] Robot connected. Waiting for camera signal...")
    # Wait for the camera thread to catch the first frame
    while shared_frame is None:
        await asyncio.sleep(0.1)

    print("[INFO] Autonomous Mode ACTIVATED. Live HD Video ready on port 5000.")
    is_escaping = False

    try:
        while True:
            await asyncio.sleep(0.01)

            # Take a snapshot of the newest frame (0 latency)
            frame = shared_frame.copy()

            # RESOLUTION IMPROVEMENT: Upscale from 400 to 600px using linear filter (sharper)
            target_width = 600
            h, w, _ = frame.shape
            target_height = int(target_width * (h / w))
            resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

            hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
            
            mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
            mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
            mask_red = cv2.bitwise_or(mask_red1, mask_red2)
            
            mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

            clean_red = cv2.dilate(cv2.erode(mask_red, kernel, iterations=2), kernel, iterations=2)
            clean_blue = cv2.dilate(cv2.erode(mask_blue, kernel, iterations=2), kernel, iterations=2)

            # --- LOGIC 1: THE RED BALL (ESCAPE) ---
            contours_red, _ = cv2.findContours(clean_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if len(contours_red) > 0 and not is_escaping:
                largest_red = max(contours_red, key=cv2.contourArea)
                ((xr, yr), radius_red) = cv2.minEnclosingCircle(largest_red)

                if radius_red > 25:
                    contour_area = cv2.contourArea(largest_red)
                    circle_area = np.pi * (radius_red ** 2)

                    if contour_area > (0.7 * circle_area):
                        cv2.circle(resized, (int(xr), int(yr)), int(radius_red), (0, 0, 255), 2)
                        print(f"[ALARM] Red ball detected! -> Escape maneuver")
                        
                        is_escaping = True
                        await robot.set_wheel_speeds(0, 0)
                        await robot.turn_right(180)
                        
                        # We no longer need the manual Buffer Flush because the background 
                        # thread keeps the image updated automatically!
                        is_escaping = False
                        continue

            # --- LOGIC 2: THE BLUE BALL (TRACKING & APPROACH) ---
            if not is_escaping:
                contours_blue, _ = cv2.findContours(clean_blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                if len(contours_blue) > 0:
                    largest_blue = max(contours_blue, key=cv2.contourArea)
                    ((xb, yb), radius_blue) = cv2.minEnclosingCircle(largest_blue)

                    if radius_blue > 10:
                        cv2.circle(resized, (int(xb), int(yb)), int(radius_blue), (255, 0, 0), 2)
                        
                        delta_x = int(xb) - 300 # The center is now 300 (since the width is 600)
                        
                        # --- CORRECTED LOGIC: PROPORTIONAL TRACKING ---
                        # 1. Calculate a proportional turn speed based on how far off-center the ball is
                        Kp = 0.02 # Proportional constant (If it still oscillates, lower to 0.015. If too slow, raise to 0.03)
                        min_turn_speed = 1.0
                        max_turn_speed = 5.0
                        
                        # Speed scales with delta_x, but is clamped between min and max speeds
                        dynamic_turn_speed = abs(delta_x) * Kp
                        dynamic_turn_speed = max(min_turn_speed, min(dynamic_turn_speed, max_turn_speed))

                        # 2. Control block with an increased deadzone (from 50 to 60)
                        if radius_blue > 90:
                            # If the radius is huge, the ball is too close. BRAKE.
                            print(f"Tracking: Blue ball reached! (Radius {int(radius_blue)}) -> BRAKING")
                            await robot.set_wheel_speeds(0, 0)
                            
                        elif delta_x < -60:
                            print(f"Tracking: Turning LEFT (Offset: {delta_x} | Speed: {dynamic_turn_speed:.1f})")
                            await robot.set_wheel_speeds(-dynamic_turn_speed, dynamic_turn_speed)
                            
                        elif delta_x > 60:
                            print(f"Tracking: Turning RIGHT (Offset: {delta_x} | Speed: {dynamic_turn_speed:.1f})")
                            await robot.set_wheel_speeds(dynamic_turn_speed, -dynamic_turn_speed)
                            
                        else:
                            # If it is centered and not too close, MOVE FORWARD towards it.
                            print("Tracking: Centered -> MOVING FORWARD towards the ball")
                            await robot.set_wheel_speeds(10, 10)
                else:
                    await robot.set_wheel_speeds(0, 0)
            else:
                await robot.set_wheel_speeds(0, 0)

            # Update the HD image for the web server
            latest_frame = resized.copy()

    except KeyboardInterrupt:
        print("\n[INFO] Manual emergency stop.")
    finally:
        await robot.set_wheel_speeds(0, 0)
        print("[INFO] All systems safely terminated.")

robot.play()

