import time
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import mss

class ScreenWorker(QThread):
    frame_ready = Signal(QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False

    def run(self):
        self.running = True
        with mss.mss() as sct:
            monitor = sct.monitors[1] # Primary monitor
            while self.running:
                try:
                    sct_img = sct.grab(monitor)
                    # Convert to numpy array
                    img_np = np.array(sct_img)
                    # MSS captures in BGRA, we want RGB for QImage (or we can use Format_RGBA8888)
                    # Let's keep it simple: drop alpha and convert to RGB
                    img_rgb = img_np[:, :, :3][:, :, ::-1] # BGRA -> BGR -> RGB
                    
                    h, w, ch = img_rgb.shape
                    bytes_per_line = ch * w
                    
                    # Create QImage
                    q_img = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
                    
                    self.frame_ready.emit(q_img)
                except Exception as e:
                    print(f"[Screen] Capture error: {e}")
                
                # ~10 FPS is enough for screen share and doesn't melt the CPU
                time.sleep(0.1)

    def stop(self):
        self.running = False
        self.wait()
