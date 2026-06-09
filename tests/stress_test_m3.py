import os
import sys
import shutil
import tempfile
import json
from pathlib import Path
import traceback

sys.path.append('c:/Users/kavs1/OneDrive/Desktop/Jarvis-main')

from actions.github_automation import github_automation
from memory.memory_manager import _empty_memory, remember, update_memory, load_memory, format_memory_for_prompt

def test_github_automation():
    print("--- Testing github_automation ---")
    temp_dir = tempfile.mkdtemp(prefix="jarvis_github_test_")
    
    try:
        # Test 1: init action
        res = github_automation({"action": "init", "path": temp_dir})
        assert "Success: Initialized git repository" in res, f"init failed: {res}"
        assert os.path.isdir(os.path.join(temp_dir, ".git")), ".git directory was not created"
        print("PASS: github_automation init")

        # Test 2: scaffold action
        res = github_automation({"action": "scaffold", "path": temp_dir})
        assert "Success: Scaffolded" in res, f"scaffold failed: {res}"
        assert os.path.exists(os.path.join(temp_dir, ".gitignore")), ".gitignore not created"
        assert os.path.exists(os.path.join(temp_dir, "README.md")), "README.md not created"
        print("PASS: github_automation scaffold")
        
        # Test 3: unknown action
        res = github_automation({"action": "hax", "path": temp_dir})
        assert "Error: Unknown action" in res, f"expected error on unknown action, got: {res}"
        print("PASS: github_automation unknown action")
        
        # Test 4: missing parameters
        res = github_automation({})
        assert "Error: Missing parameters" in res, f"expected error on missing parameters, got: {res}"
        print("PASS: github_automation missing parameters")
        
        # Test 5: stress test path traversal / malformed path
        # Let's see if scaffold crashes on invalid characters
        invalid_path = os.path.join(temp_dir, "invalid\0path")
        try:
            res = github_automation({"action": "scaffold", "path": invalid_path})
            print(f"PASS: github_automation handled invalid path gracefully (res: {res[:50]}...)")
        except Exception as e:
            print(f"FAIL: github_automation crashed on invalid path: {e}")
            raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_memory_tasks():
    print("--- Testing memory tasks ---")
    
    # Isolate memory
    original_long_term = "memory/long_term.json"
    backup_path = "memory/long_term.json.bak"
    if os.path.exists(original_long_term):
        shutil.copy(original_long_term, backup_path)
    
    try:
        # Erase current memory state for isolation
        with open(original_long_term, 'w') as f:
            json.dump(_empty_memory(), f)
            
        empty = _empty_memory()
        assert "tasks" in empty, "'tasks' not in _empty_memory"
        print("PASS: 'tasks' category exists in _empty_memory")
        
        res = remember("buy_milk", "Get 2 gallons of milk", "tasks")
        assert "Remembered: tasks/buy_milk" in res, f"remember() failed: {res}"
        print("PASS: remember() returns expected output")
        
        # reload memory to ensure it was written to disk
        mem = load_memory()
        assert "buy_milk" in mem.get("tasks", {}), "Task was not saved to long_term.json"
        assert mem["tasks"]["buy_milk"]["value"] == "Get 2 gallons of milk", "Task value is incorrect"
        print("PASS: Task saved successfully to long_term.json")
        
        # test update_memory stress
        mem = update_memory({"tasks": {"test_stress": "Value1"}})
        mem = update_memory({"tasks": {"test_stress": "Value2"}})
        assert mem["tasks"]["test_stress"]["value"] == "Value2", "Task overwrite failed"
        print("PASS: Task overwrite using update_memory works")
        
        # test format_memory_for_prompt
        prompt_txt = format_memory_for_prompt()
        assert "tasks:" in prompt_txt.lower(), "Tasks category not in prompt"
        assert "Value2" in prompt_txt, "Task value not in formatted prompt"
        print("PASS: format_memory_for_prompt includes tasks")

    finally:
        if os.path.exists(backup_path):
            shutil.move(backup_path, original_long_term)

def test_main_registration():
    print("--- Testing main registration ---")
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert "github_automation" in content, "github_automation tool not registered in main.py"
    print("PASS: github_automation found in main.py")

if __name__ == "__main__":
    try:
        test_github_automation()
        test_memory_tasks()
        test_main_registration()
        print("\nALL STRESS TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)
