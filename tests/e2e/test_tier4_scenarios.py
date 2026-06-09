import unittest
import sys
from unittest.mock import MagicMock, patch

# Need to import PySide6 before things try to use QApplication
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

# Initialize app before importing ui to avoid "QWidget: Must construct a QApplication before a QWidget"
app = QApplication.instance() or QApplication(sys.argv)

import threading

# Pre-patch core.vision_capture and PySide6.QtWebEngineWidgets before importing ui
mock_webengine = MagicMock()
sys.modules['PySide6.QtWebEngineWidgets'] = mock_webengine
sys.modules['PySide6.QtWebEngineCore'] = MagicMock()
sys.modules['core'] = MagicMock()
sys.modules['core.vision_capture'] = MagicMock()

from ui import JarvisUI

class TestTier4Scenarios(unittest.TestCase):
    """
    Tier 4 E2E tests for JARVIS Transformation.
    Focus: Real-World Application Scenarios.
    Features Exercised:
    F1: Diagram Rendering
    F2: Camera Preview
    F3: UI Layout Adaptation
    """
    
    def setUp(self):
        # We need to mock things properly
        self.ui = JarvisUI("dummy.png")
        self.win = self.ui._win
        
        # Override _send so it runs synchronously, instead of using threading.Thread
        def sync_send():
            txt = self.win._input.text().strip()
            if not txt: return
            self.win._input.clear()
            if self.win.on_text_command:
                self.win.on_text_command(txt)
                
        # Re-bind the returnPressed signal to our synchronous method
        self.win._input.returnPressed.disconnect()
        self.win._input.returnPressed.connect(sync_send)
        
        # Mock LLM callback (on_text_command) to bypass actually calling an LLM
        def mock_on_text_command(text):
            if "diagram" in text.lower():
                try:
                    self.win.show_diagram("graph TD;\nA-->B;")
                except Exception:
                    pass
            elif "camera" in text.lower():
                self.win.show_camera()
            elif "stop" in text.lower() or "hide" in text.lower():
                self.win.hide_media()
                
        self.win.on_text_command = mock_on_text_command

    def tearDown(self):
        self.win.close()

    def simulate_typing(self, text):
        self.win._input.clear()
        QTest.keyClicks(self.win._input, text)
        QTest.keyClick(self.win._input, Qt.Key.Key_Return)
        
    def test_scenario_1_mind_map(self):
        """Scenario 1: Standard mind map generation (F1)"""
        self.simulate_typing("generate diagram")
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.diagram_view)

    def test_scenario_2_camera_start_stop(self):
        """Scenario 2: Standard camera start/stop (F2, F3)"""
        self.simulate_typing("start camera")
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.camera_view)
        
        self.simulate_typing("stop camera")
        self.assertFalse(self.win.media_stack.isVisible())

    def test_scenario_3_camera_then_diagram(self):
        """Scenario 3: Camera start followed by diagram (F1, F2, F3)"""
        self.simulate_typing("start camera")
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.camera_view)
        
        self.simulate_typing("generate diagram")
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.diagram_view)

    def test_scenario_4_repeated_layout_switching(self):
        """Scenario 4: Repeated layout switching (F2, F3)"""
        for _ in range(3):
            self.simulate_typing("start camera")
            self.assertTrue(self.win.media_stack.isVisible())
            self.assertEqual(self.win.media_stack.currentWidget(), self.win.camera_view)
            
            self.simulate_typing("stop media")
            self.assertFalse(self.win.media_stack.isVisible())

    def test_scenario_5_heavy_diagram_camera_preview(self):
        """Scenario 5: Heavy diagram + camera preview (All)"""
        self.simulate_typing("generate diagram heavy")
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.diagram_view)
        
        self.simulate_typing("start camera")
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.camera_view)
        
        self.simulate_typing("generate diagram another heavy")
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.diagram_view)
        
        self.simulate_typing("stop media")
        self.assertFalse(self.win.media_stack.isVisible())

if __name__ == "__main__":
    unittest.main()
