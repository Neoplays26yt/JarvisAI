"""
system_monitor.py — JARVIS Action Module
=========================================
Provides real-time system monitoring capabilities via psutil.

Supported actions (via parameters['action']):
    snapshot      — CPU%, RAM%, disk%, network I/O snapshot.
    processes     — Top N processes by CPU or memory usage.
    kill          — Kill a process by name or PID.
    battery       — Battery level, charging status, and ETA.
    temperature   — CPU temperature readings (if sensors available).
    uptime        — Human-readable system uptime.
    startup_apps  — Windows registry startup programs (Windows only).

Dependencies:
    psutil (stdlib + winreg on Windows)
"""

import os
import sys
import time
import traceback
from datetime import datetime, timedelta

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    print("[Monitor] WARNING: psutil is not installed. "
          "Install it with: pip install psutil")

_MODULE = "Monitor"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_psutil() -> str | None:
    """Return an error string if psutil is unavailable, else None."""
    if not _PSUTIL_AVAILABLE:
        return ("Error: psutil is not installed. "
                "Install it with: pip install psutil")
    return None


def _fmt_bytes(n: int) -> str:
    """Format a byte count into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _fmt_seconds(total_seconds: float) -> str:
    """Convert a seconds value to a d h m s string."""
    total_seconds = int(total_seconds)
    days, rem     = divmod(total_seconds, 86400)
    hours, rem    = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:    parts.append(f"{days}d")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _action_snapshot() -> str:
    """Return a concise system health snapshot."""
    print(f"[{_MODULE}] Action: snapshot")

    cpu_pct  = psutil.cpu_percent(interval=0.5)
    ram      = psutil.virtual_memory()
    disk     = psutil.disk_usage("/")
    net_before = psutil.net_io_counters()
    time.sleep(0.5)
    net_after  = psutil.net_io_counters()

    net_sent = net_after.bytes_sent - net_before.bytes_sent
    net_recv = net_after.bytes_recv - net_before.bytes_recv

    lines = [
        "── System Snapshot ──────────────────────",
        f"  CPU Usage   : {cpu_pct:.1f}%",
        f"  RAM Usage   : {ram.percent:.1f}%  "
        f"({_fmt_bytes(ram.used)} / {_fmt_bytes(ram.total)})",
        f"  Disk Usage  : {disk.percent:.1f}%  "
        f"({_fmt_bytes(disk.used)} / {_fmt_bytes(disk.total)})",
        f"  Net ↑ (0.5s): {_fmt_bytes(net_sent)}/s",
        f"  Net ↓ (0.5s): {_fmt_bytes(net_recv)}/s",
        f"  Timestamp   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "─────────────────────────────────────────",
    ]
    return "\n".join(lines)


def _action_processes(parameters: dict) -> str:
    """List the top N processes sorted by CPU or memory."""
    print(f"[{_MODULE}] Action: processes")
    count   = max(1, int(parameters.get("count", 10)))
    sort_by = str(parameters.get("sort_by", "cpu")).lower()

    # Collect attributes for all processes (one-shot for efficiency)
    attrs  = ["pid", "name", "cpu_percent", "memory_percent", "status"]
    procs  = []
    for proc in psutil.process_iter(attrs=attrs):
        try:
            info = proc.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Allow a brief interval for cpu_percent to be meaningful
    time.sleep(0.2)
    for proc in psutil.process_iter(attrs=["pid", "cpu_percent"]):
        try:
            for p in procs:
                if p["pid"] == proc.info["pid"]:
                    p["cpu_percent"] = proc.info["cpu_percent"] or 0.0
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key_fn = (lambda p: p.get("memory_percent") or 0.0
              if sort_by == "memory"
              else lambda p: p.get("cpu_percent") or 0.0)
    if sort_by == "memory":
        procs.sort(key=lambda p: p.get("memory_percent") or 0.0, reverse=True)
    else:
        procs.sort(key=lambda p: p.get("cpu_percent") or 0.0, reverse=True)

    top    = procs[:count]
    header = f"Top {count} processes by {'memory' if sort_by == 'memory' else 'CPU'}:"
    lines  = [header, f"  {'PID':>7}  {'CPU%':>6}  {'MEM%':>6}  {'Status':<10}  Name"]
    lines.append("  " + "-" * 60)
    for p in top:
        lines.append(
            f"  {p.get('pid', '?'):>7}  "
            f"{(p.get('cpu_percent') or 0.0):>6.1f}  "
            f"{(p.get('memory_percent') or 0.0):>6.2f}  "
            f"{str(p.get('status', '?')):<10}  "
            f"{p.get('name', 'unknown')}"
        )
    return "\n".join(lines)


def _action_kill(parameters: dict) -> str:
    """Kill a process by name or PID."""
    print(f"[{_MODULE}] Action: kill")
    name = parameters.get("name", "")
    pid  = parameters.get("pid")

    if pid is not None:
        try:
            pid = int(pid)
            proc = psutil.Process(pid)
            proc_name = proc.name()
            proc.terminate()
            proc.wait(timeout=5)
            return f"Process '{proc_name}' (PID {pid}) terminated successfully."
        except psutil.NoSuchProcess:
            return f"No process found with PID {pid}."
        except psutil.AccessDenied:
            return f"Access denied when trying to kill PID {pid}."
        except psutil.TimeoutExpired:
            try:
                proc.kill()
                return f"Process PID {pid} force-killed (SIGKILL)."
            except Exception as exc:
                return f"Could not force-kill PID {pid}: {exc}"

    if name:
        killed = []
        errors = []
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            try:
                if proc.info["name"] and name.lower() in proc.info["name"].lower():
                    proc.terminate()
                    killed.append(f"{proc.info['name']} (PID {proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                errors.append(str(exc))
        if killed:
            msg = f"Terminated: {', '.join(killed)}."
            if errors:
                msg += f" Errors: {'; '.join(errors)}"
            return msg
        return f"No running processes matched name '{name}'."

    return "Error: provide either 'pid' or 'name' parameter to kill a process."


def _action_battery() -> str:
    """Return battery status information."""
    print(f"[{_MODULE}] Action: battery")
    battery = psutil.sensors_battery()
    if battery is None:
        return "No battery detected (desktop system or sensors unavailable)."

    pct     = battery.percent
    plugged = battery.power_plugged
    secs    = battery.secsleft

    lines = [
        "── Battery Status ───────────────────────",
        f"  Charge     : {pct:.1f}%",
        f"  Plugged In : {'Yes' if plugged else 'No'}",
    ]
    if not plugged:
        if secs == psutil.POWER_TIME_UNKNOWN:
            lines.append("  Time Left  : Unknown")
        elif secs == psutil.POWER_TIME_UNLIMITED:
            lines.append("  Time Left  : Charging / Unlimited")
        else:
            lines.append(f"  Time Left  : {_fmt_seconds(secs)}")
    lines.append("─────────────────────────────────────────")
    return "\n".join(lines)


def _action_temperature() -> str:
    """Return CPU temperature readings if available."""
    print(f"[{_MODULE}] Action: temperature")
    if not hasattr(psutil, "sensors_temperatures"):
        return "Temperature sensors are not supported on this platform."

    temps = psutil.sensors_temperatures()
    if not temps:
        return "No temperature sensors found or sensors_temperatures() returned nothing."

    lines = ["── CPU Temperature ──────────────────────"]
    for chip, entries in temps.items():
        for entry in entries:
            label   = entry.label or chip
            current = entry.current
            high    = entry.high
            crit    = entry.critical
            detail  = f"{current:.1f}°C"
            if high:
                detail += f"  (high={high:.1f}°C"
                if crit:
                    detail += f", crit={crit:.1f}°C"
                detail += ")"
            lines.append(f"  {label:<20} : {detail}")
    lines.append("─────────────────────────────────────────")
    return "\n".join(lines)


def _action_uptime() -> str:
    """Return system uptime in human-readable format."""
    print(f"[{_MODULE}] Action: uptime")
    boot_ts    = psutil.boot_time()
    boot_dt    = datetime.fromtimestamp(boot_ts)
    uptime_sec = (datetime.now() - boot_dt).total_seconds()
    return (
        f"System Uptime: {_fmt_seconds(uptime_sec)}\n"
        f"  Boot Time  : {boot_dt.strftime('%Y-%m-%d %H:%M:%S')}"
    )


def _action_startup_apps() -> str:
    """List Windows startup programs from the registry."""
    print(f"[{_MODULE}] Action: startup_apps")
    if sys.platform != "win32":
        return "Startup apps listing is only supported on Windows."

    try:
        import winreg
    except ImportError:
        return "winreg module is unavailable — cannot read startup registry."

    startup_keys = [
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ]

    entries = []
    for hive, key_path in startup_keys:
        try:
            hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
            with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        entries.append((hive_name, name, value))
                        i += 1
                    except OSError:
                        break
        except (FileNotFoundError, PermissionError):
            continue

    if not entries:
        return "No startup programs found in the registry."

    lines = [f"── Startup Programs ({len(entries)} found) ──────────────"]
    for hive_name, name, value in entries:
        val_preview = value[:70] + ("…" if len(value) > 70 else "")
        lines.append(f"  [{hive_name}] {name}")
        lines.append(f"          → {val_preview}")
    lines.append("─────────────────────────────────────────")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def system_monitor(parameters: dict, player=None, speak=None) -> str:
    """
    JARVIS system monitoring action.

    Parameters
    ----------
    parameters : dict
        Must contain 'action' key.  Additional keys depend on the action:
        - 'count'   (int) : number of processes to list (action='processes')
        - 'sort_by' (str) : 'cpu' or 'memory'          (action='processes')
        - 'name'    (str) : process name to kill        (action='kill')
        - 'pid'     (int) : process PID to kill         (action='kill')
    player : optional
        Unused; present for interface compatibility.
    speak : callable, optional
        If provided, called with the result string for TTS output.

    Returns
    -------
    str
        Human-readable result of the requested monitoring action.
    """
    action = str(parameters.get("action", "")).strip().lower()
    print(f"[{_MODULE}] Received action='{action}'")

    err = _require_psutil()
    if err and action != "startup_apps":
        if callable(speak):
            speak(err)
        return err

    try:
        if action == "snapshot":
            result = _action_snapshot()
        elif action == "processes":
            result = _action_processes(parameters)
        elif action == "kill":
            result = _action_kill(parameters)
        elif action == "battery":
            result = _action_battery()
        elif action == "temperature":
            result = _action_temperature()
        elif action == "uptime":
            result = _action_uptime()
        elif action == "startup_apps":
            result = _action_startup_apps()
        else:
            result = (
                f"Unknown monitor action: '{action}'. "
                "Valid actions: snapshot, processes, kill, battery, "
                "temperature, uptime, startup_apps."
            )
    except Exception as exc:
        print(f"[{_MODULE}] Unhandled exception: {exc}")
        print(traceback.format_exc())
        result = f"System monitor error: {exc}"

    print(f"[{_MODULE}] Result length: {len(result)} chars")
    if callable(speak):
        speak(result)
    return result
