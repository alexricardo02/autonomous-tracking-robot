import cv2
import os

def main():
    # 1. Initialize the hardware camera stream (0 is the index of the Pi camera)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("[ERROR] Cannot access the Pi camera. Check the flex cable connection.")
        return
    print("[INFO] Pi camera initialized successfully.")
    print("[INFO] Capturing calibration frame...")

    # 2. Capture a single frame
    ret, frame = cap.read()
    
    if ret:
        # --- THE PERFORMANCE TRICK ---
        # We scale the frame down to a fixed, low width (600 pixels).
        # Fewer pixels reduce the Pi's workload exponentially (limited resources).
        target_width = 600
        
        # Preserve the original aspect ratio to avoid distorting the ball
        h, w, _ = frame.shape
        aspect_ratio = h / w
        target_height = int(target_width * aspect_ratio)
        
        # Geometric scaling optimized using area interpolation
        resized_frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
        
        # Display debug metrics in the CLI
        print(f" -> Native resolution detected: {w}x{h}")
        print(f" -> Optimized resolution for processing: {target_width}x{target_height}")
        
        # --- HEADLESS ENVIRONMENT STRATEGY ---
        # Since we operate without a graphical interface, cv2.imshow() would crash.
        # We save the capture as a physical image file instead.
        output_filename = "test_capture.jpg"
        cv2.imwrite(output_filename, resized_frame)
        
        print(f"[SUCCESS] Frame processed and saved as '{output_filename}' in the current directory.")
    else:
        print("[ERROR] Failed to capture video data from the buffer.")

    # 3. Release the camera sensor resource (mandatory on embedded systems)
    cap.release()
    print("[INFO] Camera resource released successfully.")

if __name__ == "__main__":
    main()
