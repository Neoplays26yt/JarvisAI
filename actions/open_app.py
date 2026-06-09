import time
import subprocess
import platform
import shutil

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    return raw  

def _launch_windows(app_name: str) -> bool:

    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    if ":" in app_name:
        try:
            subprocess.Popen(f"start {app_name}", shell=True)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.7)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.9)
        pyautogui.press("enter")
        time.sleep(2.5)
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


def _launch_linux(app_name: str) -> bool:

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

# ── Close-App Helpers ─────────────────────────────────────────────────────────

_CLOSE_NAMES: dict[str, list[str]] = {
    "chrome":             ["chrome.exe", "chrome"],
    "google chrome":      ["chrome.exe", "chrome"],
    "firefox":            ["firefox.exe", "firefox"],
    "edge":               ["msedge.exe", "msedge"],
    "brave":              ["brave.exe", "brave"],
    "spotify":            ["spotify.exe", "spotify"],
    "vlc":                ["vlc.exe", "vlc"],
    "discord":            ["discord.exe", "discord"],
    "slack":              ["slack.exe", "slack"],
    "zoom":               ["zoom.exe", "zoom"],
    "teams":              ["teams.exe", "ms-teams.exe", "msteams"],
    "vscode":             ["code.exe", "code"],
    "visual studio code": ["code.exe", "code"],
    "code":               ["code.exe", "code"],
    "notepad":            ["notepad.exe", "notepad"],
    "steam":              ["steam.exe", "steam"],
    "whatsapp":           ["whatsapp.exe", "whatsapp"],
    "telegram":           ["telegram.exe"],
    "explorer":           ["explorer.exe"],
    "postman":            ["postman.exe"],
    "obs":                ["obs64.exe", "obs32.exe", "obs.exe", "obs"],
    "terminal":           ["wt.exe", "wt"],
    "powershell":         ["powershell.exe", "pwsh.exe"],
    "cmd":                ["cmd.exe"],
    "task manager":       ["taskmgr.exe"],
    "word":               ["winword.exe"],
    "excel":              ["excel.exe"],
    "powerpoint":         ["powerpnt.exe"],
    "paint":              ["mspaint.exe"],
    "capcut":             ["capcut.exe"],
    "epic":               ["epicgameslauncher.exe"],
    "epic games":         ["epicgameslauncher.exe"],
    "notion":             ["notion.exe"],
    "obsidian":           ["obsidian.exe"],
}


def _close_app_psutil(app_name: str) -> list[str]:
    """
    Close all processes matching app_name.
    Returns list of process names that were terminated.
    """
    if not _PSUTIL:
        return []

    key = app_name.lower().strip()
    # Build a set of candidate process name fragments to match
    candidates: set[str] = set()
    candidates.add(key.replace(" ", ""))
    candidates.add(key.replace(" ", "_"))
    candidates.add(key.replace(" ", "-"))

    # Look up predefined aliases
    for alias, names in _CLOSE_NAMES.items():
        if alias in key or key in alias:
            for n in names:
                candidates.add(n.lower())

    killed = []
    import time as _time

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = proc.info["name"]
            if not pname:
                continue
            pname_lower = pname.lower()
            # Match if any candidate is a substring of the process name or vice versa
            match = any(c in pname_lower or pname_lower in c for c in candidates)
            # Also direct partial match
            if not match:
                match = key in pname_lower or pname_lower.startswith(key[:5])
            if match:
                print(f"[close_app] Terminating {pname} (PID {proc.pid})...")
                try:
                    proc.terminate()
                    killed.append(pname)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    # Give processes a moment to exit, then force-kill survivors
    if killed:
        _time.sleep(1.2)
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = proc.info["name"]
                if pname and pname in killed:
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    return killed


def _close_app_taskkill(app_name: str) -> bool:
    """Fallback: use taskkill on Windows."""
    key = app_name.lower().strip()
    names = []
    for alias, ns in _CLOSE_NAMES.items():
        if alias in key or key in alias:
            names.extend(ns)
    if not names:
        names = [key, key + ".exe"]

    any_ok = False
    for n in names:
        try:
            r = subprocess.run(
                ["taskkill", "/f", "/im", n],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                any_ok = True
        except Exception:
            pass
    return any_ok


def close_app_action(app_name: str, player=None) -> str:
    """Close a running application by name."""
    if not app_name:
        return "No application name provided."

    print(f"[close_app] Closing: '{app_name}'")
    if player:
        try:
            player.write_log(f"[close_app] {app_name}")
        except Exception:
            pass

    killed = _close_app_psutil(app_name)
    if killed:
        names = ", ".join(set(killed))
        return f"Closed {app_name} ({names})."

    # Fallback: taskkill (Windows)
    if _SYSTEM == "Windows":
        if _close_app_taskkill(app_name):
            return f"Closed {app_name}."

    # macOS fallback
    if _SYSTEM == "Darwin":
        try:
            # Try AppleScript quit
            normalized = _normalize(app_name)
            result = subprocess.run(
                ["osascript", "-e", f'quit app "{normalized}"'],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return f"Closed {app_name}."
        except Exception:
            pass

    return (
        f"Could not find a running process for '{app_name}'. "
        "It may already be closed, or the name might be spelled differently."
    )


# ── Entry Point ───────────────────────────────────────────────────────────────

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    JARVIS app launcher and closer.

    parameters:
        action   : 'open' | 'close' (default: 'open')
        app_name : Application name to open or close
    """
    p        = parameters or {}
    action   = p.get("action", "open").strip().lower()
    app_name = p.get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    # ── Close ──────────────────────────────────────────────────────────────────
    if action == "close":
        return close_app_action(app_name, player)

    # ── Open (default) ────────────────────────────────────────────────────────
    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = _normalize(app_name)
    print(f"[open_app] Launching: '{app_name}' → '{normalized}' ({_SYSTEM})")

    if player:
        try:
            player.write_log(f"[open_app] {app_name}")
        except Exception:
            pass

    try:
        if launcher(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower():
            if launcher(app_name):
                return f"Opened {app_name}."
        return (
            f"Could not confirm that {app_name} launched. "
            f"It may still be loading, or it might not be installed."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"
