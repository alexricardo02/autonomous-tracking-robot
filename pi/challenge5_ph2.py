import cv2

def main():
    stream_url = "tcp://127.0.0.1:8888"
    cap = cv2.VideoCapture(stream_url)
    
    if not cap.isOpened():
        print("[ERROR] Failed to connect to the video server.")
        return

    print("[INFO] Stream connected successfully. Starting live processing...")
    saved_test_image = False

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Scaling (performance trick)
            target_width = 600
            h, w, _ = frame.shape
            aspect_ratio = h / w
            target_height = int(target_width * aspect_ratio)
            resized_frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
            
            # HSV conversion
            hsv_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2HSV)
            
            if not saved_test_image:
                cv2.imwrite("test_hsv.jpg", hsv_frame)
                print("[SUCCESS] First HSV test image saved as 'test_hsv.jpg'!")
                saved_test_image = True

    except KeyboardInterrupt:
        print("\n[INFO] Processing interrupted by user.")

    cap.release()
    print("[INFO] Camera resources released successfully.")

if __name__ == "__main__":
    main()
