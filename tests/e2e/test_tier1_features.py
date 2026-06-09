import unittest
import sys
import types
from unittest.mock import patch, MagicMock

# Ensure QApplication is initialized before importing PySide6 components
from PySide6.QtWidgets import QApplication, QWidget, QLabel
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt, QObject, Signal

app = QApplication.instance() or QApplication(sys.argv)

# Mock QtWebEngineWidgets if missing
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    class DummyWebEngineView(QWidget):
        def setHtml(self, html):
            self.html = html
    sys.modules['PySide6.QtWebEngineWidgets'] = types.ModuleType('PySide6.QtWebEngineWidgets')
    sys.modules['PySide6.QtWebEngineWidgets'].QWebEngineView = DummyWebEngineView
    sys.modules['PySide6.QtWebEngineCore'] = types.ModuleType('PySide6.QtWebEngineCore')
    sys.modules['PySide6.QtWebEngineCore'].QWebEnginePage = MagicMock()

# We also mock cv2 in case it is imported by core.vision_capture and not installed
try:
    import cv2
except ImportError:
    sys.modules['cv2'] = MagicMock()

from ui import JarvisUI

class MockCameraWorkerSignals(QObject):
    frame_ready = Signal(QImage)

class MockCameraWorker(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sigs = MockCameraWorkerSignals()
        self.frame_ready = self.sigs.frame_ready
    
    def start(self):
        self.started = True
        
    def stop(self):
        self.stopped = True

class TestTier1Features(unittest.TestCase):
    def setUp(self):
        self.ui = JarvisUI("dummy_path")
        self.win = self.ui._win

    def tearDown(self):
        self.win.hide()
        self.win.deleteLater()

    # --- Feature 1: Diagram Rendering ---

    def test_diagram_lazy_initialization(self):
        self.assertIsNone(self.win.diagram_view)
        self.assertFalse(self.win.media_stack.isVisible())

    def test_diagram_show_creates_webengineview(self):
        self.win.show_diagram("graph TD\nA-->B")
        self.assertIsNotNone(self.win.diagram_view)
        # It should be added to media_stack
        self.assertIn(self.win.diagram_view, [self.win.media_stack.widget(i) for i in range(self.win.media_stack.count())])

    def test_diagram_stack_visibility(self):
        self.win.show_diagram("graph TD\nA-->B")
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.diagram_view)

    def test_diagram_hide_media(self):
        self.win.show_diagram("graph TD\nA-->B")
        self.assertTrue(self.win.media_stack.isVisible())
        self.win.hide_media()
        self.assertFalse(self.win.media_stack.isVisible())

    def test_diagram_repeated_updates(self):
        self.win.show_diagram("graph TD\nA-->B")
        first_view = self.win.diagram_view
        self.win.show_diagram("graph TD\nC-->D")
        self.win.show_diagram("graph TD\nE-->F")
        # Should reuse the same view
        self.assertEqual(self.win.diagram_view, first_view)
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.diagram_view)
        self.assertTrue(self.win.media_stack.isVisible())

    # --- Feature 2: Camera Preview ---

    def test_camera_view_exists_on_init(self):
        self.assertIsNotNone(self.win.camera_view)
        self.assertIsInstance(self.win.camera_view, QLabel)

    @patch('core.vision_capture.CameraWorker', MockCameraWorker)
    def test_camera_show_starts_worker(self):
        self.win.show_camera()
        self.assertIsNotNone(getattr(self.win, '_camera_worker', None))
        self.assertTrue(getattr(self.win._camera_worker, 'started', False))

    @patch('core.vision_capture.CameraWorker', MockCameraWorker)
    def test_camera_stack_visibility(self):
        self.win.show_camera()
        self.assertTrue(self.win.media_stack.isVisible())
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.camera_view)

    @patch('core.vision_capture.CameraWorker', MockCameraWorker)
    def test_camera_frame_update_simulated(self):
        self.win.show_camera()
        worker = self.win._camera_worker
        # Simulate frame emission
        test_image = QImage(100, 100, QImage.Format.Format_RGB888)
        test_image.fill(Qt.GlobalColor.red)
        worker.frame_ready.emit(test_image)
        # Process events so the signal is handled
        QApplication.processEvents()
        
        pixmap = self.win.camera_view.pixmap()
        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())

    @patch('core.vision_capture.CameraWorker', MockCameraWorker)
    def test_camera_hide_stops_worker(self):
        self.win.show_camera()
        worker = self.win._camera_worker
        self.win.hide_media()
        self.assertFalse(self.win.media_stack.isVisible())
        self.assertIsNone(self.win._camera_worker)
        self.assertTrue(getattr(worker, 'stopped', False))

    # --- Feature 3: UI Layout Adaptation ---

    def test_layout_stretch_factors(self):
        center_lay = self.win._center_widget.layout()
        # media_stack is at index 0, hud at index 1
        self.assertEqual(center_lay.stretch(0), 8)
        self.assertEqual(center_lay.stretch(1), 2)

    def test_hud_persists_during_media(self):
        self.assertTrue(self.win.hud.isVisible())
        self.win.show_diagram("graph TD\nA-->B")
        self.assertTrue(self.win.hud.isVisible())
        
    @patch('core.vision_capture.CameraWorker', MockCameraWorker)
    def test_media_stack_switch(self):
        self.win.show_camera()
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.camera_view)
        
        self.win.show_diagram("graph TD\nA-->B")
        self.assertEqual(self.win.media_stack.currentWidget(), self.win.diagram_view)
        self.assertTrue(self.win.media_stack.isVisible())

    def test_window_minimum_size(self):
        self.assertEqual(self.win.minimumWidth(), 820)
        self.assertEqual(self.win.minimumHeight(), 580)

    def test_fullscreen_toggle(self):
        is_fs = self.win.isFullScreen()
        self.win._toggle_fullscreen()
        self.assertNotEqual(self.win.isFullScreen(), is_fs)
        self.win._toggle_fullscreen()
        self.assertEqual(self.win.isFullScreen(), is_fs)

if __name__ == '__main__':
    unittest.main()
