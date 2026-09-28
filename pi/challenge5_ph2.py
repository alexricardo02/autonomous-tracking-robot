import cv2

def main():
    stream_url = "tcp://127.0.0.1:8888"
    cap = cv2.VideoCapture(stream_url)
    
    if not cap.isOpened():
        print("[ERROR] Verbindung zum Videoserver fehlgeschlagen.")
        return

    print("[INFO] Stream erfolgreich verbunden. Starte Live-Verarbeitung...")
    saved_test_image = False

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Skalierung (Performance-Trick)
            target_width = 600
            h, w, _ = frame.shape
            aspect_ratio = h / w
            target_height = int(target_width * aspect_ratio)
            resized_frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
            
            # HSV-Konvertierung
            hsv_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2HSV)
            
            if not saved_test_image:
                cv2.imwrite("test_hsv.jpg", hsv_frame)
                print("[SUCCESS] Erstes HSV-Testbild als 'test_hsv.jpg' gespeichert!")
                saved_test_image = True

    except KeyboardInterrupt:
        print("\n[INFO] Verarbeitung vom Nutzer abgebrochen.")

    cap.release()
    print("[INFO] Kamera-Ressourcen erfolgreich freigegeben.")

if __name__ == "__main__":
    main()
