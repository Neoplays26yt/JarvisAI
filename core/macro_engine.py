import json
import os
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

from agent.executor import _call_tool

def get_base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

class MacroEngine:
    def __init__(self):
        self.base_dir = get_base_dir()
        self.config_dir = self.base_dir / "config"
        self.config_path = self.config_dir / "macros.json"
        self.macros = {}
        self._load()

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.macros = json.load(f)
            except json.JSONDecodeError:
                self.macros = {}
        else:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.macros = {}
            self._save()

    def _save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.macros, f, indent=4)
            
    def list_macros(self) -> Dict[str, Any]:
        return self.macros
        
    def create_macro(self, name: str, description: str, steps: List[Dict[str, Any]]):
        if name in self.macros:
            raise ValueError(f"Macro '{name}' already exists.")
            
        for step in steps:
            if "tool" not in step:
                raise ValueError("Each step must have a 'tool' key.")
                
        self.macros[name] = {
            "description": description,
            "steps": steps
        }
        self._save()

    def edit_macro(self, name: str, description: Optional[str] = None, steps: Optional[List[Dict[str, Any]]] = None):
        if name not in self.macros:
            raise ValueError(f"Macro '{name}' not found.")
            
        if description is not None:
            self.macros[name]["description"] = description
        if steps is not None:
            for step in steps:
                if "tool" not in step:
                    raise ValueError("Each step must have a 'tool' key.")
            self.macros[name]["steps"] = steps
            
        self._save()

    def delete_macro(self, name: str):
        if name not in self.macros:
            raise ValueError(f"Macro '{name}' not found.")
            
        del self.macros[name]
        self._save()

    def execute_macro(
        self, 
        name: str, 
        speak: Optional[Callable] = None, 
        cancel_flag: Optional[threading.Event] = None,
        callback: Optional[Callable] = None
    ) -> threading.Thread:
        if name not in self.macros:
            raise ValueError(f"Macro '{name}' not found.")
        
        macro = self.macros[name]
        steps = macro.get("steps", [])

        def _run():
            print(f"[MacroEngine] 🚀 MACRO_START  name={name}  steps={len(steps)}")
            if speak:
                speak(f"Running macro {name}, sir.")
            failed_step = None
            for idx, step in enumerate(steps):
                if cancel_flag and cancel_flag.is_set():
                    print(f"[MacroEngine] 🛑 MACRO_CANCEL  name={name}  at_step={idx+1}")
                    if speak:
                        speak(f"Macro {name} was cancelled at step {idx + 1}, sir.")
                    break

                tool   = step.get("tool")
                params = step.get("parameters", {})
                # print(f"[MacroEngine] ▶️ MACRO_STEP  name={name}  step={idx+1}/{len(steps)}  tool={tool}")
                try:
                    result = _call_tool(tool, params, speak)
                    # print(f"[MacroEngine] ✅ MACRO_STEP_OK  name={name}  step={idx+1}  result={str(result)[:80]}")
                    if callback:
                        callback(idx, result)
                except Exception as e:
                    err_msg = str(e)
                    # print(f"[MacroEngine] ❌ MACRO_STEP_FAIL  name={name}  step={idx+1}  tool={tool}  err={err_msg[:100]}")
                    failed_step = idx + 1
                    if speak:
                        speak(
                            f"Sir, macro {name} failed at step {idx + 1} — {tool} reported: {err_msg[:80]}. "
                            "Stopping the macro."
                        )
                    if callback:
                        callback(idx, e)
                    break

            if failed_step is None:
                print(f"[MacroEngine] ✅ MACRO_DONE  name={name}")
                if speak:
                    speak(f"Macro {name} completed all {len(steps)} steps, sir.")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread
