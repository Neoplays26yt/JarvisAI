import unittest
import sys
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QThread

# Initialize app before importing ui to avoid "QWidget: Must construct a QApplication before a QWidget"
app = QApplication.instance() or QApplication(sys.argv)

class DummyWebEngineView(QWidget):
    def setHtml(self, html):
        pass

class DummyWebEngineCore:
    class QWebEnginePage:
        pass

class MockCameraWorker(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame_ready = MagicMock()
    def start(self):
        pass
    def stop(self):
        pass

# Setup mock modules for testing
mock_vision_capture = MagicMock()
mock_vision_capture.CameraWorker = MockCameraWorker

mock_qtwebenginewidgets = MagicMock()
mock_qtwebenginewidgets.QWebEngineView = DummyWebEngineView

# We patch sys.modules before importing ui so that inside ui it uses these mocked modules.
with patch.dict('sys.modules', {
    'core': MagicMock(),
    'core.vision_capture': mock_vision_capture,
    'PySide6.QtWebEngineWidgets': mock_qtwebenginewidgets,
    'PySide6.QtWebEngineCore': DummyWebEngineCore
}):
    from ui import MainWindow

class TestTier3Combinations(unittest.TestCase):
    """
    Tier 3 E2E tests for JARVIS Transformation.
    Focus: Cross-Feature Combinations (pairwise coverage).
    Features:
    F1: Diagram Rendering
    F2: Camera Preview
    F3: UI Layout Adaptation
    """
    
    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        # We use a dummy face image path
        # Re-apply the patch in case imports happen dynamically during test
        self.patcher = patch.dict('sys.modules', {
            'core': MagicMock(),
            'core.vision_capture': mock_vision_capture,
            'PySide6.QtWebEngineWidgets': mock_qtwebenginewidgets,
            'PySide6.QtWebEngineCore': DummyWebEngineCore
        })
        self.patcher.start()
        
        self.window = MainWindow("dummy.png")
        # Ensure window is shown so that isVisible() evaluates to True
        self.window.show()

    def tearDown(self):
        self.window.close()
        self.patcher.stop()

    def test_f1_f2_diagram_then_camera(self):
        """Test Case 1: Diagram (F1) followed by Camera (F2)."""
        # Show Diagram (F1)
        self.window.show_diagram("graph TD;\nA-->B;")
        self.assertTrue(self.window.media_stack.isVisible())
        self.assertEqual(self.window.media_stack.currentWidget(), self.window.diagram_view)
            
        # Show Camera (F2)
        self.window.show_camera()
        self.assertTrue(self.window.media_stack.isVisible())
        self.assertEqual(self.window.media_stack.currentWidget(), self.window.camera_view)
        
    def test_f2_f1_camera_then_diagram(self):
        """Test Case 2: Camera (F2) followed by Diagram (F1)."""
        self.window.show_camera()
        self.assertTrue(self.window.media_stack.isVisible())
        self.assertEqual(self.window.media_stack.currentWidget(), self.window.camera_view)
        
        self.window.show_diagram("graph TD;\nA-->B;")
        self.assertTrue(self.window.media_stack.isVisible())
        self.assertEqual(self.window.media_stack.currentWidget(), self.window.diagram_view)

    def test_f2_f3_camera_layout_switch(self):
        """Test Case 3: Camera (F2) and UI Layout Adaptation (F3) repeated switching."""
        self.window.show_camera()
        self.assertTrue(self.window.media_stack.isVisible())
        
        self.window.hide_media()
        self.assertFalse(self.window.media_stack.isVisible())
        
        self.window.show_camera()
        self.assertTrue(self.window.media_stack.isVisible())

    def test_f1_f3_diagram_layout_switch(self):
        """Test Case 4: Diagram (F1) and UI Layout Adaptation (F3) repeated switching."""
        self.window.show_diagram("graph TD;\nA-->B;")
        self.assertTrue(self.window.media_stack.isVisible())
        
        self.window.hide_media()
        self.assertFalse(self.window.media_stack.isVisible())
        
        self.window.show_diagram("graph TD;\nC-->D;")
        self.assertTrue(self.window.media_stack.isVisible())
        self.assertEqual(self.window.media_stack.currentWidget(), self.window.diagram_view)

if __name__ == "__main__":
    unittest.main()
