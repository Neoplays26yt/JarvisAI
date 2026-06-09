"""
weather_report.py — Real weather data via wttr.in API for JARVIS.

Uses wttr.in's JSON API for actual weather data instead of opening a browser.
Falls back to browser redirect if API is unavailable.
"""

import json
import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path


_CONDITION_ICONS = {
    "sunny": "☀️",
    "clear": "☀️",
    "partly cloudy": "⛅",
    "cloudy": "☁️",
    "overcast": "☁️",
    "mist": "🌫️",
    "fog": "🌫️",
    "rain": "🌧️",
    "drizzle": "🌦️",
    "snow": "❄️",
    "sleet": "🌨️",
    "thunder": "⛈️",
    "blizzard": "🌨️",
    "wind": "💨️",
    "storm": "⛈️",
}


def _condition_icon(desc: str) -> str:
    dl = desc.lower()
    for kw, icon in _CONDITION_ICONS.items():
        if kw in dl:
            return icon
    return "🌡️"


def _fetch_wttr(city: str, units: str = "m") -> dict | None:
    """
    Fetch weather JSON from wttr.in.
    Returns parsed dict or None on failure.
    units: 'm' = metric (°C), 'u' = US (°F), 'M' = wind in m/s
    """
    encoded = urllib.parse.quote_plus(city)
    url = f"https://wttr.in/{encoded}?format=j1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[Weather] ⚠️ wttr.in fetch failed: {e}")
        return None


def _parse_weather(data: dict, city: str, units: str = "m") -> str:
    """Format wttr.in JSON response into a readable string."""
    try:
        current = data["current_condition"][0]
        temp_c  = current.get("temp_C", "?")
        temp_f  = current.get("temp_F", "?")
        feels_c = current.get("FeelsLikeC", "?")
        feels_f = current.get("FeelsLikeF", "?")
        humidity = current.get("humidity", "?")
        wind_kmph = current.get("windspeedKmph", "?")
        wind_dir  = current.get("winddir16Point", "?")
        visibility = current.get("visibility", "?")
        uv_index = current.get("uvIndex", "?")

        desc_list = current.get("weatherDesc", [{}])
        desc = desc_list[0].get("value", "Unknown") if desc_list else "Unknown"
        icon = _condition_icon(desc)

        temp_str = f"{temp_c}°C / {temp_f}°F"
        feels_str = f"{feels_c}°C / {feels_f}°F"

        lines = [
            f"{icon}  Weather for {city.title()}",
            f"   Condition  : {desc}",
            f"   Temperature: {temp_str}",
            f"   Feels like : {feels_str}",
            f"   Humidity   : {humidity}%",
            f"   Wind       : {wind_kmph} km/h {wind_dir}",
            f"   Visibility : {visibility} km",
            f"   UV Index   : {uv_index}",
        ]

        # Add 3-day forecast if available
        weather_days = data.get("weather", [])[:3]
        if weather_days:
            lines.append("")
            lines.append("📅  3-Day Forecast:")
            for day in weather_days:
                date     = day.get("date", "?")
                max_c    = day.get("maxtempC", "?")
                min_c    = day.get("mintempC", "?")
                max_f    = day.get("maxtempF", "?")
                min_f    = day.get("mintempF", "?")
                hourly   = day.get("hourly", [{}])
                day_desc = ""
                if hourly:
                    mid = hourly[len(hourly) // 2]
                    descs = mid.get("weatherDesc", [{}])
                    day_desc = descs[0].get("value", "") if descs else ""
                day_icon = _condition_icon(day_desc)
                lines.append(
                    f"   {date}: {day_icon} {day_desc} | "
                    f"{min_c}–{max_c}°C / {min_f}–{max_f}°F"
                )

        return "\n".join(lines)

    except Exception as e:
        print(f"[Weather] ⚠️ Parse error: {e}")
        return None


def _browser_fallback(city: str, when: str = "today") -> str:
    """Open Google weather in browser as fallback."""
    import webbrowser
    from urllib.parse import quote_plus
    query = f"weather in {city} {when}"
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    try:
        webbrowser.open(url)
        return f"Opened browser weather for {city}, {when}."
    except Exception as e:
        return f"Could not fetch or display weather for {city}: {e}"


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"WEATHER: {message}")
        except Exception:
            pass


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    JARVIS weather tool — real data via wttr.in API.

    parameters:
        city  : City name (required)
        when  : today | tomorrow | weekend (used in browser fallback, default: today)
        units : m (metric/°C) | u (imperial/°F) | default: m
    """
    city  = (parameters.get("city") or "").strip()
    when  = (parameters.get("time", "") or parameters.get("when", "today")).strip()
    units = (parameters.get("units", "m") or "m").strip().lower()

    if not city:
        msg = "The city is missing for the weather report, sir."
        _log(msg, player)
        return msg

    _log(f"Fetching weather for {city!r}...", player)

    # Try real API first
    data = _fetch_wttr(city, units)
    if data:
        result = _parse_weather(data, city, units)
        if result:
            _log(f"Weather data received for {city}", player)
            return result

    # Fallback to browser
    _log(f"API unavailable — opening browser for {city}", player)
    return _browser_fallback(city, when)
