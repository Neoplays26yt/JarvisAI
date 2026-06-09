"""
homework_assistant.py — JARVIS Action Module
============================================
Handles academic requests, homework structuring, and solution guidance.
"""

_MODULE = "HomeworkAssist"

def activate_homework_mode(parameters: dict, player=None, speak=None) -> str:
    """
    Action module to engage homework assistance mode.
    """
    subject = parameters.get("subject", "General Academic")
    
    # Send a prompt structured for homework support
    msg = f"Homework Assistant Mode Activated for {subject}.\n\n" \
          f"To provide the best help, please tell me:\n" \
          f"1. What is your current grade/level?\n" \
          f"2. Are there any specific rubrics or constraints for this assignment?\n" \
          f"3. Where are you currently stuck?\n\n" \
          f"I will not just give you the final answer; I will guide you step-by-step so you can learn!"
          
    if callable(speak):
        speak("Homework mode activated. Let's tackle this assignment together.")
        
    return msg
