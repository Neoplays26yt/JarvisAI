from pathlib import Path
import time

def camera_control(parameters: dict, player) -> str:
    action = parameters.get("action", "")
    
    assets_dir = Path("assets/captures")
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    ui_obj = player
    if hasattr(player, '_win'):
        ui_obj = player._win
    elif hasattr(player, 'ui'):
        ui_obj = player.ui
        
    if action == "start":
        if ui_obj:
            from PySide6.QtCore import QMetaObject, Qt  # type: ignore
            QMetaObject.invokeMethod(ui_obj, "show_camera", Qt.ConnectionType.QueuedConnection)
            if hasattr(player, 'write_log'): player.write_log("Camera: Live feed started")
            elif hasattr(ui_obj, 'write_log'): ui_obj.write_log("Camera: Live feed started")
            return "Live camera feed started with object detection."
        return "UI not available to show camera."
        
    elif action == "stop":
        if ui_obj:
            from PySide6.QtCore import QMetaObject, Qt #type: ignore
            QMetaObject.invokeMethod(ui_obj, "hide_media", Qt.ConnectionType.QueuedConnection)
            if hasattr(player, 'write_log'): player.write_log("Camera: Live feed stopped")
            elif hasattr(ui_obj, 'write_log'): ui_obj.write_log("Camera: Live feed stopped")
            return "Live camera feed stopped."
        return "UI not available to hide camera."
        
    worker = getattr(ui_obj, '_camera_worker', None) if ui_obj else None
    
    if not worker:
        return "Camera is not currently active. I need to open it first."
        
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
