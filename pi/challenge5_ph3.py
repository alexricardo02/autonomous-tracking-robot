import cv2
import numpy as np

def main():
    stream_url = "tcp://127.0.0.1:8888"
    cap = cv2.VideoCapture(stream_url)
    
    if not cap.isOpened():
        print("[ERROR] Video server not reachable.")
        return

    print("[INFO] Phase 3 active. Filtering and morphological cleanup...")

    # HSV color range values determined experimentally
    lower_blue = np.array([100, 50, 50])
    upper_blue = np.array([130, 255, 255])
    lower_red = np.array([0, 150, 100])
    upper_red = np.array([10, 255, 255])

    # Elliptical kernel for morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    saved_masks = False

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            target_width = 600
            h, w, _ = frame.shape
            target_height = int(target_width * (h / w))
            resized_frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
            
            hsv = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2HSV)
            
            # Masking
            mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
            mask_red = cv2.inRange(hsv, lower_red, upper_red)
            
            # Morphological cleanup (erosion followed by dilation)
            cleaned_blue = cv2.erode(mask_blue, kernel, iterations=2)
            cleaned_blue = cv2.dilate(cleaned_blue, kernel, iterations=2)
            
            cleaned_red = cv2.erode(mask_red, kernel, iterations=2)
            cleaned_red = cv2.dilate(cleaned_red, kernel, iterations=2)
            
            if not saved_masks:
                cv2.imwrite("mask_blue_cleaned.jpg", cleaned_blue)
                cv2.imwrite("mask_red_cleaned.jpg", cleaned_red)
                print("[SUCCESS] Cleaned masks saved successfully!")
                saved_masks = True

    except KeyboardInterrupt:
        print("\n[INFO] Aborted.")

    cap.release()

if __name__ == "__main__": main() 
