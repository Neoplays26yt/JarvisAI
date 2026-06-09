import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import psutil

from agent.orchestrator import get_orchestrator_state

class WorkspaceManager:
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces: Dict[str, Dict[str, Any]] = {}
        self.load_workspaces()

    def load_workspaces(self):
        self.workspaces.clear()
        if not self.config_dir.exists():
            return
        for file_path in self.config_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    name = data.get("name", file_path.stem)
                    self.workspaces[name] = data
            except Exception as e:
                print(f"[WorkspaceManager] Error loading {file_path}: {e}")

    def _is_process_running(self, process_name: str) -> bool:
        process_name = process_name.lower()
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == process_name:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def activate_workspace(self, name: str) -> bool:
        if name not in self.workspaces:
            print(f"[WorkspaceManager] Workspace '{name}' not found.")
            return False
            
        workspace_data = self.workspaces[name]
        
        # 1. Close apps
        close_apps = workspace_data.get("close_apps", [])
        if close_apps:
            for proc in psutil.process_iter(['name']):
                try:
                    proc_name = proc.info['name']
                    if proc_name:
                        for app_to_close in close_apps:
                            if app_to_close.lower() in proc_name.lower():
                                print(f"[WorkspaceManager] Closing {proc_name}...")
                                proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        
        # 2. Launch apps
        apps = workspace_data.get("apps", [])
        for app in apps:
            process_name = app.get("process_name")
            if process_name and self._is_process_running(process_name):
                print(f"[WorkspaceManager] App {process_name} is already running.")
                continue
                
            launch_cmd = app.get("launch_cmd")
            path = app.get("path")
            
            try:
                if launch_cmd:
                    print(f"[WorkspaceManager] Launching with cmd: {launch_cmd}")
                    subprocess.Popen(launch_cmd, shell=True)
                elif path:
                    print(f"[WorkspaceManager] Launching with path: {path}")
                    os.startfile(path)
            except Exception as e:
                print(f"[WorkspaceManager] Error launching app {app}: {e}")

        # 3. Update orchestrator state
        get_orchestrator_state().active_workspace = workspace_data
        print(f"[WorkspaceManager] Workspace '{name}' activated.")
        return True
