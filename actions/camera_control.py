from pathlib import Path
import time

def camera_control(parameters: dict, player) -> str:
    action = parameters.get("action", "")
    
    worker = getattr(player, '_camera_worker', None)
    if not worker:
        return "Camera is not currently active. I need to open it first."

    assets_dir = Path("assets/captures")
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    if action == "start":
        if player and hasattr(player, '_win'):
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(player._win, "show_camera", Qt.ConnectionType.QueuedConnection)
            player.write_log("Camera: Live feed started")
            return "Live camera feed started with object detection."
        return "UI not available to show camera."
        
    elif action == "stop":
        if player and hasattr(player, '_win'):
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(player._win, "hide_media", Qt.ConnectionType.QueuedConnection)
            player.write_log("Camera: Live feed stopped")
            return "Live camera feed stopped."
        return "UI not available to hide camera."
        
    if action == "take_photo":
        filename = assets_dir / f"photo_{timestamp}.jpg"
        worker.capture_photo(str(filename))
        player.write_log(f"Camera: Saved photo to {filename.name}")
        return f"I have taken a picture and saved it as {filename.name}."
        
    elif action == "start_recording":
        filename = assets_dir / f"video_{timestamp}.mp4"
        worker.start_recording(str(filename))
        player.write_log(f"Camera: Started recording to {filename.name}")
        return "Video recording started."
        
    elif action == "stop_recording":
        worker.stop_recording()
        player.write_log("Camera: Stopped recording")
        return "Video recording stopped and saved."
        
    return "Unknown camera action."
