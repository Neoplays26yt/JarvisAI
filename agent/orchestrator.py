import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class IntentResponse:
    intent: str
    confidence: float
    mode: str
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    needs_clarification: bool = False
    needs_confirmation: bool = False
    final_response: Optional[str] = None
    safety_status: str = "safe"

class OrchestratorState:
    def __init__(self):
        self.pending_confirmation: Optional[Dict[str, Any]] = None
        self.active_workspace: Optional[Dict[str, Any]] = None
        
    def require_confirmation(self, tool_name: str, args: Dict[str, Any]) -> str:
        self.pending_confirmation = {
            "tool_name": tool_name,
            "args": args
        }
        return f"Warning: Execution of '{tool_name}' is a destructive/risky action. Please ask the user for explicit confirmation before proceeding."
        
    def clear_confirmation(self):
        self.pending_confirmation = None

# Global state for the session
_global_state = OrchestratorState()

def get_orchestrator_state() -> OrchestratorState:
    return _global_state

def is_risky_action(tool_name: str, args: Dict[str, Any]) -> bool:
    if tool_name == "file_controller":
        action = args.get("action", "")
        if action in ("delete", "write", "move", "rename"):
            return True
    elif tool_name == "computer_control":
        # Only block actions that can cause irreversible / surprising behaviour.
        # Safe actions (screenshot, type, scroll, move, wait) do NOT require confirmation.
        action = args.get("action", "")
        dangerous_actions = {
            "hotkey",   # can trigger destructive OS shortcuts
            "press",    # can submit forms, delete content
            "click",    # can click destructive UI elements
            "double_click",
            "right_click",
            "screen_click",  # AI-driven clicking on unknown targets
        }
        if action in dangerous_actions:
            return True
    elif tool_name == "send_message":
        return True
    elif tool_name == "shutdown_jarvis":
        return True
    elif tool_name == "generated_code":
        return True
    return False

def format_structured_intent(json_str: str) -> Optional[IntentResponse]:
    try:
        data = json.loads(json_str)
        return IntentResponse(**data)
    except Exception as e:
        print(f"[Orchestrator] ⚠️ Failed to parse structured intent: {e}")
        return None
