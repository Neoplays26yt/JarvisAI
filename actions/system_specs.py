"""
system_specs.py — JARVIS Action Module
======================================
Provides detailed hardware specifications and OS awareness.
"""

import platform
import psutil
import subprocess

_MODULE = "SystemSpecs"

def get_system_specs(parameters: dict, player=None, speak=None) -> str:
    """
    Returns detailed system specifications including CPU, RAM, OS, and Motherboard.
    """
    os_name = platform.system()
    os_release = platform.release()
    os_arch = platform.machine()
    
    cpu_info = platform.processor() or "Unknown CPU"
    cpu_cores = psutil.cpu_count(logical=False)
    cpu_threads = psutil.cpu_count(logical=True)
    
    mem = psutil.virtual_memory()
    total_ram_gb = round(mem.total / (1024 ** 3), 2)
    
    gpu_info = "Unknown GPU"
    if os_name == "Windows":
        try:
            r = subprocess.run(
                ["powershell", "-Command", "(Get-WmiObject Win32_VideoController).Name"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0 and r.stdout.strip():
                gpu_info = r.stdout.strip().replace('\n', ', ')
        except Exception:
            pass
            
    mobo_info = "Unknown Motherboard"
    if os_name == "Windows":
        try:
            r = subprocess.run(
                ["powershell", "-Command", "(Get-WmiObject Win32_BaseBoard).Product"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0 and r.stdout.strip():
                mobo_info = r.stdout.strip().replace('\n', ', ')
        except Exception:
            pass

    result = (
        f"🖥️ System Specifications:\n"
        f"- OS: {os_name} {os_release} ({os_arch})\n"
        f"- CPU: {cpu_info} ({cpu_cores} cores, {cpu_threads} threads)\n"
        f"- RAM: {total_ram_gb} GB\n"
        f"- GPU: {gpu_info}\n"
        f"- Motherboard: {mobo_info}\n"
    )
    
    print(f"[{_MODULE}] Fetched specs.")
    if callable(speak):
        speak(f"System is running {os_name} on a {total_ram_gb} GB machine with a {cpu_threads} thread processor.")
        
    return result
