"""Main application window — assembles all UI components."""

from collections import deque
import numpy as np

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QApplication

from ui.theme import DARK, LIGHT, ThemePalette
from ui.controls_bar import ControlsBar
from ui.preview_widget import PreviewWidget
from ui.transcription_tray import TranscriptionTray
from ui.history_sidebar import HistorySidebar
from ui.side_menu import SideMenu
from ui.components import StatusBar


class MainWindow(QMainWindow):
    engine_changed = pyqtSignal(str)
    recapture_requested = pyqtSignal()
    tts_requested = pyqtSignal(str)
    translate_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DesktopOCR")
        self.setMinimumSize(900, 600)
        self.resize(1280, 720)

        # Frame queue for preview widget
        self._frame_queue = deque(maxlen=1)

        # Controls bar (top)
        self.controls_bar = ControlsBar(["paddle", "easyocr", "windows_ocr"])
        self.setMenuWidget(self.controls_bar)

        # Central widget: left column (preview + tray) + right column (history)
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left column
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.preview_widget = PreviewWidget(self._frame_queue)
        self.transcription_tray = TranscriptionTray()

        left_layout.addWidget(self.preview_widget, stretch=1)
        left_layout.addWidget(self.transcription_tray)

        main_layout.addWidget(left_widget, stretch=1)

        # Right column
        self.history_sidebar = HistorySidebar()
        main_layout.addWidget(self.history_sidebar)

        # Status bar (native)
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)

        # Side menu overlay (hidden by default)
        self.side_menu = SideMenu(self)
        self.side_menu.setVisible(False)

        # Wire internal signals to MainWindow signals
        self.controls_bar.menu_requested.connect(self._toggle_side_menu)
        self.controls_bar.engine_changed.connect(self.engine_changed.emit)
        self.transcription_tray.recapture_requested.connect(self.recapture_requested.emit)
        self.transcription_tray.tts_requested.connect(self.tts_requested.emit)
        self.history_sidebar.tts_requested.connect(self.tts_requested.emit)
        self.history_sidebar.translate_requested.connect(self.translate_requested.emit)
        self.side_menu.theme_changed.connect(self._apply_theme)
        self.side_menu.hide_requested.connect(self.side_menu.hide)

        # Detect and apply system theme on startup
        self._detect_and_apply_theme()

    # --- Theme handling ---

    def _detect_system_theme(self) -> ThemePalette:
        app = QApplication.instance()
        if app is None:
            return DARK
        hints = app.styleHints()
        is_dark = hints.colorScheme() == Qt.ColorScheme.Dark
        return DARK if is_dark else LIGHT

    def _detect_and_apply_theme(self):
        pal = self._detect_system_theme()
        self._apply_pal(pal)

    def _apply_theme(self, theme_id: str):
        if theme_id == "dark":
            pal = DARK
        elif theme_id == "light":
            pal = LIGHT
        else:  # auto
            pal = self._detect_system_theme()
        self._apply_pal(pal)

    def _apply_pal(self, pal: ThemePalette):
        self.setStyleSheet(f"background: {pal.bg};")
        self.controls_bar.set_theme(pal)
        self.transcription_tray.set_theme(pal)
        self.history_sidebar.set_theme(pal)
        self.side_menu.set_theme(pal)
        self.status_bar.set_theme(pal)
        self.preview_widget.set_theme(pal)

    # --- Side menu positioning ---

    def _toggle_side_menu(self):
        self.side_menu.setVisible(not self.side_menu.isVisible())
        self._position_side_menu()

    def _position_side_menu(self):
        if not self.side_menu.isVisible():
            return
        bar_height = self.menuWidget().height() if self.menuWidget() else 48
        self.side_menu.setGeometry(
            0,
            bar_height,
            self.side_menu.width(),
            self.centralWidget().height(),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_side_menu()

    # --- Public API for main.py ---

    def set_ocr_result(self, text: str, confidence: float, engine: str, timestamp: str):
        self.transcription_tray.set_ocr_text(text)
        self.history_sidebar.add_entry(timestamp, engine, confidence, text)

    def set_preview_frame(self, frame: np.ndarray | None):
        if frame is not None:
            self._frame_queue.append(frame.copy())

    def set_status(self, engine: str, fps: float, conf: float, window_title: str):
        self.status_bar.set_engine(engine)
        self.status_bar.set_fps(fps)
        self.status_bar.set_confidence(conf)
        self.status_bar.set_window_title(window_title)
