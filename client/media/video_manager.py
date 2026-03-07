import cv2
import threading
import base64
import time

class VideoManager:
    def __init__(self):
        self.cap = None
        self.running = False
        self.frame_callback = None

    def start_capture(self, callback):
        self.frame_callback = callback
        self.running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def stop_capture(self):
        self.running = False
        if self.cap:
            self.cap.release()

    def _capture_loop(self):
        self.cap = cv2.VideoCapture(0)
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                # Resize for performance
                frame = cv2.resize(frame, (320, 240))
                # Compress to JPEG with lower quality (50) to reduce bandwidth
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                jpg_as_text = buffer.tobytes()
                if self.frame_callback:
                    self.frame_callback(jpg_as_text)
            
            # Limit to ~20 FPS to avoid network saturation
            time.sleep(0.05)

    def decode_frame(self, data):
        # Data is bytes (JPEG)
        # We need to convert to image for Tkinter
        # This will be handled by GUI, here we just return raw bytes or numpy array if needed
        # But actually, GUI needs PIL Image or PhotoImage.
        # Let's return the raw bytes, GUI handles display.
        return data
