"""
focus_mode.py — JARVIS Action Module
======================================
Manages Pomodoro-style focus sessions with optional system configuration.

Supported actions (via parameters['action']):
    start          — Begin a focus session; optionally lower volume & close apps.
    status         — Display time remaining and session goal.
    stop           — End the session early and show a summary.
    schedule_break — Announce an upcoming break in N minutes.

Session state is persisted to ~/.jarvis/focus_session.json so JARVIS can
query it across restarts.

Parameters:
    start:
        duration  (int)        : Session length in minutes (default: 25).
        goal      (str)        : Goal description (default: 'Focus session').
        close_apps (list[str]) : Process name prefixes to terminate on start.

    status:    (no extra parameters)

    stop:      (no extra parameters)

    schedule_break:
        minutes  (int) : Minutes until break is announced (default: 5).

Logs with [Focus] prefix.
"""

import json
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    print("[Focus] WARNING: psutil not installed — app-closing feature disabled.")

_MODULE       = "Focus"
_JARVIS_DIR   = Path.home() / ".jarvis"
_SESSION_FILE = _JARVIS_DIR / "focus_session.json"

# Processes considered distracting (used when close_apps is not specified).
_DEFAULT_DISTRACTING_APPS: list[str] = []  # populated by caller via close_apps


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_dir() -> None:
    """Create ~/.jarvis if it does not exist."""
    _JARVIS_DIR.mkdir(parents=True, exist_ok=True)


def _load_session() -> dict | None:
    """Return the session dict from disk, or None if no session exists."""
    try:
        if _SESSION_FILE.exists():
            with open(_SESSION_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception as exc:
        print(f"[{_MODULE}] Could not read session file: {exc}")
    return None


def _save_session(session: dict) -> None:
    """Persist the session dict to disk."""
    _ensure_dir()
    try:
        with open(_SESSION_FILE, "w", encoding="utf-8") as fh:
            json.dump(session, fh, indent=2)
    except Exception as exc:
        print(f"[{_MODULE}] Could not write session file: {exc}")


def _delete_session() -> None:
    """Remove the session file if it exists."""
    try:
        if _SESSION_FILE.exists():
            _SESSION_FILE.unlink()
    except Exception as exc:
        print(f"[{_MODULE}] Could not delete session file: {exc}")


def _set_volume_windows(percent: int) -> str:
    """
    Attempt to set system volume on Windows.

    Tries nircmd first (if on PATH), then falls back to a PowerShell
    Audio COM approach.  Returns a status message.
    """
    if sys.platform != "win32":
        return ""

    # Approach 1: nircmd (fastest / most reliable if installed)
    try:
        # nircmd uses a 0–65535 scale
        nircmd_val = int(percent / 100 * 65535)
        result = subprocess.run(
            ["nircmd", "setsysvolume", str(nircmd_val)],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            print(f"[{_MODULE}] Volume set to {percent}% via nircmd.")
            return f"System volume set to {percent}% (via nircmd)."
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # nircmd not available, fall through

    # Approach 2: PowerShell via Windows Audio API
    ps_script = (
        f"$wshShell = New-Object -ComObject WScript.Shell; "
        f"$vol = [Math]::Round({percent}/100*100); "
        f"(New-Object -ComObject Shell.Application).Windows() | "
        f"ForEach-Object {{}}; "
        # Use SoundVolumeView or just mute/unmute pattern
        f"$code = @\"\n"
        f"Add-Type -TypeDefinition @'\n"
        f"using System.Runtime.InteropServices;\n"
        f"[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\")]\n"
        f"[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        f"interface IAudioEndpointVolume {{\n"
        f"  int _(int a, int b); int __(int a); int ___(int a);\n"
        f"  int GetMasterVolumeLevelScalar(out float p);\n"
        f"  int SetMasterVolumeLevelScalar(float p, System.Guid e);\n"
        f"}}\n"
        f"'@\n"
        f"\"@"
    )
    # Simplified — use the reliable SendKeys mute workaround is impractical.
    # Instead use a straightforward PowerShell nircmd-free volume setter:
    try:
        vol_fraction = percent / 100.0
        ps = (
            "Add-Type -TypeDefinition '"
            "using System.Runtime.InteropServices; "
            "public class Vol { "
            "[DllImport(\"winmm.dll\")] public static extern int waveOutSetVolume(IntPtr h, uint v); "
            "}'; "
            f"$v = [uint32]({int(vol_fraction * 65535)} + ({int(vol_fraction * 65535)} * 0x10000)); "
            "[Vol]::waveOutSetVolume([IntPtr]::Zero, $v);"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=10,
        )
        print(f"[{_MODULE}] Volume set to {percent}% via PowerShell waveOut.")
        return f"System volume set to {percent}% (via PowerShell)."
    except Exception as exc:
        print(f"[{_MODULE}] Volume set failed: {exc}")
        return f"Volume adjustment skipped ({exc})."


def _close_apps(app_names: list) -> list[str]:
    """
    Terminate processes whose names match any entry in app_names.
    Returns a list of successfully terminated process names.
    """
    if not _PSUTIL_AVAILABLE or not app_names:
        return []

    terminated = []
    for proc in psutil.process_iter(attrs=["pid", "name"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            for target in app_names:
                if target.lower() in pname:
                    proc.terminate()
                    terminated.append(proc.info["name"])
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return terminated


def _fmt_duration(total_seconds: float) -> str:
    """Return a human-readable duration string."""
    total_seconds = max(0, int(total_seconds))
    hours, rem    = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _action_start(parameters: dict) -> str:
    """Start a new focus session."""
    print(f"[{_MODULE}] Action: start")

    # Check for an existing active session
    existing = _load_session()
    if existing:
        end_dt  = datetime.fromisoformat(existing["end_time"])
        if datetime.now() < end_dt:
            remaining = (end_dt - datetime.now()).total_seconds()
            return (
                f"A focus session is already active!\n"
                f"  Goal     : {existing.get('goal')}\n"
                f"  Remaining: {_fmt_duration(remaining)}\n"
                "Use action='stop' to end it first."
            )

    duration_min = int(parameters.get("duration", 25))
    goal         = str(parameters.get("goal", "Focus session"))
    close_apps   = parameters.get("close_apps", [])

    if duration_min <= 0:
        return "Error: 'duration' must be a positive integer (minutes)."

    start_time = datetime.now()
    end_time   = start_time + timedelta(minutes=duration_min)

    session = {
        "start_time":      start_time.isoformat(timespec="seconds"),
        "end_time":        end_time.isoformat(timespec="seconds"),
        "duration_minutes": duration_min,
        "goal":            goal,
    }
    _save_session(session)
    print(f"[{_MODULE}] Session saved: goal='{goal}' duration={duration_min}m")

    lines = [
        "🎯 Focus session started!",
        f"  Goal     : {goal}",
        f"  Duration : {duration_min} minutes",
        f"  Ends at  : {end_time.strftime('%H:%M:%S')}",
    ]

    # Set volume on Windows
    vol_msg = _set_volume_windows(20)
    if vol_msg:
        lines.append(f"  Volume   : {vol_msg}")

    # Close distracting apps
    if close_apps:
        terminated = _close_apps(close_apps)
        if terminated:
            lines.append(f"  Closed   : {', '.join(terminated)}")
        else:
            lines.append("  Apps     : No matching processes found to close.")

    lines.append("\nGood luck — stay focused! 💪")
    return "\n".join(lines)


def _action_status() -> str:
    """Display current session status."""
    print(f"[{_MODULE}] Action: status")
    session = _load_session()
    if not session:
        return "No active focus session found. Use action='start' to begin one."

    end_dt    = datetime.fromisoformat(session["end_time"])
    start_dt  = datetime.fromisoformat(session["start_time"])
    now       = datetime.now()
    remaining = (end_dt - now).total_seconds()
    elapsed   = (now - start_dt).total_seconds()

    if remaining <= 0:
        return (
            f"⏰ Focus session has ended!\n"
            f"  Goal    : {session.get('goal')}\n"
            f"  Elapsed : {_fmt_duration(elapsed)}\n"
            "Use action='stop' to clear the session."
        )

    return (
        f"🎯 Focus session in progress\n"
        f"  Goal      : {session.get('goal')}\n"
        f"  Started   : {start_dt.strftime('%H:%M:%S')}\n"
        f"  Ends at   : {end_dt.strftime('%H:%M:%S')}\n"
        f"  Elapsed   : {_fmt_duration(elapsed)}\n"
        f"  Remaining : {_fmt_duration(remaining)}"
    )


def _action_stop() -> str:
    """Stop the current focus session and return a summary."""
    print(f"[{_MODULE}] Action: stop")
    session = _load_session()
    if not session:
        return "No active focus session to stop."

    start_dt = datetime.fromisoformat(session["start_time"])
    end_dt   = datetime.fromisoformat(session["end_time"])
    now      = datetime.now()

    elapsed_sec   = (now - start_dt).total_seconds()
    planned_sec   = session.get("duration_minutes", 0) * 60
    completed_pct = min(100.0, (elapsed_sec / planned_sec * 100) if planned_sec > 0 else 0)

    _delete_session()
    print(f"[{_MODULE}] Session stopped after {_fmt_duration(elapsed_sec)}")

    return (
        f"✅ Focus session ended.\n"
        f"  Goal       : {session.get('goal')}\n"
        f"  Planned    : {session.get('duration_minutes')} minutes\n"
        f"  Completed  : {_fmt_duration(elapsed_sec)} ({completed_pct:.0f}%)\n"
        "Great work — take a break! ☕"
    )


def _action_schedule_break(parameters: dict) -> str:
    """Inform the user that a break is coming in N minutes."""
    print(f"[{_MODULE}] Action: schedule_break")
    minutes = int(parameters.get("minutes", 5))
    if minutes <= 0:
        return "Error: 'minutes' must be a positive integer."

    break_time = datetime.now() + timedelta(minutes=minutes)
    return (
        f"⏱️  Break scheduled in {minutes} minute{'s' if minutes != 1 else ''}.\n"
        f"  Break at   : {break_time.strftime('%H:%M:%S')}\n"
        "Keep going — you're almost there! 🏁"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def focus_mode(parameters: dict, player=None, speak=None) -> str:
    """
    JARVIS focus mode manager.

    Manages Pomodoro-style focus sessions stored as a JSON file at
    ~/.jarvis/focus_session.json.  On Windows, attempts to lower system volume
    at session start using nircmd (if available) or a PowerShell fallback.

    Parameters
    ----------
    parameters : dict
        action        (str)       : 'start', 'status', 'stop', 'schedule_break'.
        duration      (int)       : Session length in minutes (default: 25).
        goal          (str)       : Session goal description.
        close_apps    (list[str]) : Process name substrings to terminate on start.
        minutes       (int)       : Minutes until break (action='schedule_break').
    player : optional
        Unused; present for interface compatibility.
    speak : callable, optional
        If provided, called with the result string for TTS output.

    Returns
    -------
    str
        Human-readable result of the requested focus action.
    """
    action = str(parameters.get("action", "")).strip().lower()
    print(f"[{_MODULE}] Received action='{action}'")

    try:
        if action == "start":
            result = _action_start(parameters)
        elif action == "status":
            result = _action_status()
        elif action == "stop":
            result = _action_stop()
        elif action == "schedule_break":
            result = _action_schedule_break(parameters)
        else:
            result = (
                f"Unknown focus action: '{action}'. "
                "Valid actions: start, status, stop, schedule_break."
            )
    except Exception as exc:
        print(f"[{_MODULE}] Unhandled exception: {exc}")
        print(traceback.format_exc())
        result = f"Focus mode error: {exc}"

    print(f"[{_MODULE}] Result: {result[:120]}")
    if callable(speak):
        speak(result)
    return result
