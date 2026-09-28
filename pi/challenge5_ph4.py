import cv2
import numpy as np

def main():
    stream_url = "tcp://127.0.0.1:8888"
    cap = cv2.VideoCapture(stream_url)
    
    if not cap.isOpened():
        return

    print("[INFO] Phase 4 aktiv. Berechne Ballkoordinaten...")
    lower_blue = np.array([100, 50, 50])
    upper_blue = np.array([130, 255, 255])
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    saved_tracking_image = False

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
            mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
            cleaned_blue = cv2.dilate(cv2.erode(mask_blue, kernel, iterations=2), kernel, iterations=2)
            
            contours, _ = cv2.findContours(cleaned_blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if len(contours) > 0:
                largest_contour = max(contours, key=cv2.contourArea)
                ((x, y), radius) = cv2.minEnclosingCircle(largest_contour)
                
                if radius > 10:
                    center = (int(x), int(y))
                    delta_x = int(x) - 300
                    
                    print(f"[TRACKING] X: {center[0]} | Y: {center[1]} | Radius: {int(radius)} | Offset: {delta_x}")
                    
                    # Zeichnen der Overlays für das Debugging
                    cv2.circle(resized_frame, center, int(radius), (0, 255, 0), 2)
                    cv2.circle(resized_frame, center, 5, (0, 0, 255), -1)
                    
                    if not saved_tracking_image:
                        cv2.imwrite("test_tracking.jpg", resized_frame)
                        saved_tracking_image = True
            else:
                print("[INFO] Kein Ball im Sichtfeld.")

    except KeyboardInterrupt:
        print("\n[INFO] Beendet.")
    cap.release()

if __name__ == "__main__":
    main()
