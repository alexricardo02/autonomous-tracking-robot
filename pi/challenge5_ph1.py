import cv2
import os

def main():
    # 1. Hardware-Stream der Kamera initialisieren (0 ist der Index der Pi-Kamera)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("[FEHLER] Zugriff auf die Pi-Kamera nicht möglich. Prüft die Flex-Kabelverbindung.")
        return
    print("[INFO] Pi-Kamera korrekt initialisiert.")
    print("[INFO] Steuerungs-Frame wird erfasst...")

    # 2. Ein einzelnes Bild (Frame) erfassen
    ret, frame = cap.read()
    
    if ret:
        # --- DER PERFORMANCE-TRICK ---
        # Wir skalieren das Frame auf eine feste, geringe Breite (600 Pixel)
        # Weniger Pixel reduzieren die Arbeitslast auf der Pi exponentiell (eingeschränkte Ressourcen)
        target_width = 600
        
        # Beibehaltung des ursprünglichen Seitenverhältnisses, um Verformungen des Balls zu vermeiden
        h, w, _ = frame.shape
        aspect_ratio = h / w
        target_height = int(target_width * aspect_ratio)
        
        # Geometrische Skalierung optimiert durch Flächeninterpolation
        resized_frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
        
        # Debug-Metriken in der CLI anzeigen
        print(f" -> Native Auflösung erkannt: {w}x{h}")
        print(f" -> Optimierte Auflösung für die Verarbeitung: {target_width}x{target_height}")
        
        # --- STRATEGIE FÜR HEADLESS-UMGEBUNG ---
        # Da wir ohne grafische Oberfläche operieren, würde cv2.imshow() abstürzen.
        # Wir speichern die Aufnahme als physische Bilddatei.
        output_filename = "test_capture.jpg"
        cv2.imwrite(output_filename, resized_frame)
        
        print(f"[ERFOLG] Frame verarbeitet und als '{output_filename}' im aktuellen Verzeichnis gespeichert.")
    else:
        print("[FEHLER] Fehler bei der Erfassung der Videodaten aus dem Puffer.")

    # 3. Kamerasensor-Ressource freigeben (zwingend erforderlich bei eingebetteten Systemen)
    cap.release()
    print("[INFO] Kamera-Ressource korrekt freigegeben.")

if __name__ == "__main__":
    main()
