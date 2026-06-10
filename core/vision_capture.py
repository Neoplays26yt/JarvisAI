import cv2
import numpy as np
import urllib.request
import os
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import concurrent.futures

class CameraWorker(QThread):
    frame_ready = Signal(QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.cap = None
        
        self.model_dir = Path.home() / '.jarvis' / 'models'
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.prototxt = self.model_dir / "MobileNetSSD_deploy.prototxt"
        self.caffemodel = self.model_dir / "MobileNetSSD_deploy.caffemodel"
        
        self.CLASSES = ["background", "aeroplane", "bicycle", "bird", "boat",
            "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
            "dog", "horse", "motorbike", "person", "pottedplant", "sheep",
            "sofa", "train", "tvmonitor"]
        self.COLORS = np.random.uniform(0, 255, size=(len(self.CLASSES), 3))
        self.net = None
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._future = None
        self._last_detections = None
        self._last_dims = None
        
        # Tracking states
        self.tracked_objects = {}  # tid -> {box, idx, conf, misses}
        self.next_track_id = 0
        self.max_misses = 8
        self.ema_alpha = 0.2
        # Capture states
        self.trigger_photo = False
        self.photo_path = ""
        self.is_recording = False
        self.video_writer = None
        self.video_path = ""

    def _ensure_model(self):
        if not self.prototxt.exists():
            print("[Vision] Downloading MobileNet-SSD Prototxt...")
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.prototxt",
                self.prototxt
            )
        if not self.caffemodel.exists():
            print("[Vision] Downloading MobileNet-SSD Caffemodel...")
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.caffemodel",
                self.caffemodel
            )

    def run(self):
        try:
            self._ensure_model()
            self.net = cv2.dnn.readNetFromCaffe(str(self.prototxt), str(self.caffemodel))
            # Use CAP_DSHOW on Windows to prevent MSMF grabFrame warnings
            import os
            if os.name == 'nt':
                self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            else:
                self.cap = cv2.VideoCapture(0)
            self.running = True

            frame_count = 0
            fail_count = 0
            import time
            while self.running:
                ret, frame = self.cap.read()
                if not ret or frame is None or frame.size == 0:
                    fail_count += 1
                    if fail_count > 10:
                        print("[Vision] Camera signal lost. Reconnecting...")
                        self.cap.release()
                        time.sleep(1)
                        if os.name == 'nt':
                            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                        else:
                            self.cap = cv2.VideoCapture(0)
                        fail_count = 0
                    self.msleep(30)
                    continue
                fail_count = 0

                if self._future is None or self._future.done():
                    if self._future is not None and self._future.done():
                        try:
                            self._last_detections = self._future.result()
                            self._last_dims = getattr(self, '_current_dims', frame.shape[:2])
                            self._update_tracker(self._last_detections, self._last_dims[0], self._last_dims[1])
                        except Exception as e:
                            print(f"[Vision] Forward pass error: {e}")
                            
                    (h, w) = frame.shape[:2]
                    self._current_dims = (h, w)
                    blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
                    self.net.setInput(blob)
                    self._future = self.executor.submit(self.net.forward)

                # Draw tracked objects
                for tid, t_obj in list(self.tracked_objects.items()):
                    if t_obj['misses'] > 2:  # Hide temporarily if missing for a few frames
                        continue
                    (startX, startY, endX, endY) = t_obj['box']
                    idx = t_obj['idx']
                    conf = t_obj['conf']
                    label = f"{self.CLASSES[idx]}: {conf * 100:.2f}%"
                    cv2.rectangle(frame, (startX, startY), (endX, endY), self.COLORS[idx], 2)
                    y = startY - 15 if startY - 15 > 15 else startY + 15
                    cv2.putText(frame, label, (startX, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.COLORS[idx], 2)

                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                
                # Handling photo capture
                if self.trigger_photo:
                    try:
                        cv2.imwrite(self.photo_path, frame)
                        print(f"[Vision] Photo saved: {self.photo_path}")
                    except Exception as e:
                        print(f"[Vision] Photo save failed: {e}")
                    self.trigger_photo = False
                    
                # Handling video recording
                if self.is_recording:
                    if self.video_writer is None:
                        try:
                            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                            self.video_writer = cv2.VideoWriter(self.video_path, fourcc, 20.0, (w, h))
                        except Exception as e:
                            print(f"[Vision] Video init failed: {e}")
                            self.is_recording = False
                    if self.video_writer is not None:
                        self.video_writer.write(frame)
                else:
                    if self.video_writer is not None:
                        self.video_writer.release()
                        self.video_writer = None

                self.frame_ready.emit(q_img.copy())
                self.msleep(30)
                
        except Exception as e:
            print(f"[Vision] Error: {e}")
        finally:
            if self.cap:
                self.cap.release()
            if self.video_writer:
                self.video_writer.release()

    def _update_tracker(self, detections, h, w):
        new_objects = []
        for i in np.arange(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > 0.5:
                idx = int(detections[0, 0, i, 1])
                box = (detections[0, 0, i, 3:7] * np.array([w, h, w, h])).astype("int")
                new_objects.append({'box': box, 'idx': idx, 'conf': confidence})

        matched_new = set()
        matched_tracked = set()

        for tid, t_obj in self.tracked_objects.items():
            best_dist = float('inf')
            best_new_idx = -1
            tcx = (t_obj['box'][0] + t_obj['box'][2]) / 2
            tcy = (t_obj['box'][1] + t_obj['box'][3]) / 2

            for ni, n_obj in enumerate(new_objects):
                if ni in matched_new or n_obj['idx'] != t_obj['idx']:
                    continue
                ncx = (n_obj['box'][0] + n_obj['box'][2]) / 2
                ncy = (n_obj['box'][1] + n_obj['box'][3]) / 2
                dist = np.sqrt((tcx - ncx)**2 + (tcy - ncy)**2)
                
                if dist < 120 and dist < best_dist:
                    best_dist = dist
                    best_new_idx = ni

            if best_new_idx != -1:
                matched_new.add(best_new_idx)
                matched_tracked.add(tid)
                alpha = self.ema_alpha
                t_obj['box'] = (t_obj['box'] * alpha + new_objects[best_new_idx]['box'] * (1 - alpha)).astype("int")
                t_obj['conf'] = new_objects[best_new_idx]['conf']
                t_obj['misses'] = 0
            else:
                t_obj['misses'] += 1

        self.tracked_objects = {tid: t_obj for tid, t_obj in self.tracked_objects.items() if t_obj['misses'] <= self.max_misses}

        for ni, n_obj in enumerate(new_objects):
            if ni not in matched_new:
                self.tracked_objects[self.next_track_id] = {'box': n_obj['box'], 'idx': n_obj['idx'], 'conf': n_obj['conf'], 'misses': 0}
                self.next_track_id += 1

    def stop(self):
        self.running = False
        self.is_recording = False
        self.wait()
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)

    def capture_photo(self, filepath: str):
        self.photo_path = filepath
        self.trigger_photo = True

    def start_recording(self, filepath: str):
        self.video_path = filepath
        self.is_recording = True

    def stop_recording(self):
        self.is_recording = False
