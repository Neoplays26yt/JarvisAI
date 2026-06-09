"""
screen_share.py — JARVIS Action Module
======================================
Provides live screen sharing capabilities.
"""

_MODULE = "ScreenShare"

def screen_share_control(parameters: dict, player=None, speak=None) -> str:
    """
    Action module to interface with screen sharing.
    Supported actions:
      - 'start': start live screen share mode
      - 'stop': stop live screen share mode
    """
    action = parameters.get("action", "start").lower().strip()
    
    if action == "start":
        if player and hasattr(player, '_win'):
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(player._win, "show_screen_share", Qt.ConnectionType.QueuedConnection)
            msg = "Live screen share feed started."
            if callable(speak): speak(msg)
            return msg
        return "UI not available to show screen."
        
    elif action == "stop":
        if player and hasattr(player, '_win'):
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(player._win, "hide_media", Qt.ConnectionType.QueuedConnection)
            msg = "Live screen share feed stopped."
            if callable(speak): speak(msg)
            return msg
        return "UI not available to hide screen."
        
    return f"Unknown screen share action: {action}"
