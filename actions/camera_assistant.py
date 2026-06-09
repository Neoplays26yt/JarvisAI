"""
camera_assistant.py — JARVIS Action Module
==========================================
Provides webcam capture capabilities.
"""

import cv2
from pathlib import Path
from datetime import datetime
import base64

_MODULE = "CameraAssist"

def camera_control(parameters: dict, player=None, speak=None) -> str:
    """
    Action module to interface with the webcam.
    Supported actions:
      - 'capture': takes a photo from the default webcam and saves it to Desktop.
    """
    action = parameters.get("action", "capture").lower().strip()
    
    if action == "start":
        if player and hasattr(player, '_win'):
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(player._win, "show_camera", Qt.ConnectionType.QueuedConnection)
            msg = "Live camera feed started with object detection."
            if callable(speak): speak(msg)
            return msg
        return "UI not available to show camera."
        
    elif action == "stop":
        if player and hasattr(player, '_win'):
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(player._win, "hide_media", Qt.ConnectionType.QueuedConnection)
            msg = "Live camera feed stopped."
            if callable(speak): speak(msg)
            return msg
        return "UI not available to hide camera."
        
    elif action == "capture":
        import threading
        
        def capture_thread():
            try:
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    if callable(speak): speak("Error: Could not open the webcam.")
                    return
                    
                ret, frame = cap.read()
                cap.release()
                
                if not ret:
                    if callable(speak): speak("Error: Could not read frame from webcam.")
                    return
                    
                desktop = Path.home() / "Desktop"
                filename = f"jarvis_camera_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                filepath = desktop / filename
                
                cv2.imwrite(str(filepath), frame)
                print(f"[{_MODULE}] Photo saved to Desktop as {filename}")
                
                if callable(speak):
                    speak("I've taken a photo using your webcam, sir.")
            except Exception as e:
                print(f"[{_MODULE}] Error capturing photo: {str(e)}")
                
        threading.Thread(target=capture_thread, daemon=True).start()
        return "Capturing photo..."
    return f"Unknown camera action: {action}"
