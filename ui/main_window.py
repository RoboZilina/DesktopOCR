"""Main application window — assembles all UI components."""

import asyncio
import logging
from collections import deque
import numpy as np

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QApplication

from ui.theme import DARK, LIGHT, ThemePalette, apply_theme
from ui.controls_bar import ControlsBar
from ui.preview_widget import PreviewWidget
from ui.transcription_tray import TranscriptionTray
from ui.history_sidebar import HistorySidebar
from ui.side_menu import SideMenu
from ui.components import StatusBar
from core.translation.manager import TranslationManager
from core.translation.deepl_backend import DeepLBackend
from core.translation.google_backend import GoogleTranslateBackend

_logger = logging.getLogger(__name__)


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
        self.controls_bar._menu_btn.raise_()

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
        # Wire tray translate button → MainWindow.translate_requested
        self.transcription_tray.translate_requested.connect(self.translate_requested.emit)
        self.side_menu.theme_changed.connect(self._apply_theme)
        self.side_menu.hide_requested.connect(self.side_menu.hide)

        # Translation manager — DeepL primary, Google fallback
        self._libre_url = "http://localhost:5000"
        self._translation_manager = TranslationManager([
            DeepLBackend(),
            GoogleTranslateBackend(),
        ])

        # Wire translate_requested → async handler
        self.translate_requested.connect(
            lambda text: asyncio.create_task(
                self._on_translate_requested(text)
            )
        )

        # Wire SideMenu translation signals
        self.side_menu.translation_enabled_changed.connect(
            self._on_translation_enabled_changed
        )
        self.side_menu.translation_backend_changed.connect(
            self._on_translation_backend_changed
        )
        self.side_menu.libre_url_changed.connect(
            self._on_libre_url_changed
        )

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
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, pal)
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
        available_h = self.centralWidget().height()
        # Side menu fills the full available height — scroll area handles overflow
        self.side_menu.setGeometry(
            0,
            bar_height,
            self.side_menu.width(),
            available_h,
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

    # --- Translation ---

    async def _on_translate_requested(self, text: str) -> None:
        """Async handler: translate text and update the tray."""
        if not text or not text.strip():
            return

        self.transcription_tray.set_translating(True)
        try:
            result = await self._translation_manager.translate(text)
        except Exception as exc:  # noqa: BLE001 — belt-and-suspenders
            _logger.error("[MainWindow] Translation raised unexpectedly: %s", exc)
            result = ""

        if result:
            self.transcription_tray.set_translation(result)
            self.transcription_tray.set_translating(False)
        else:
            self.transcription_tray.set_translation_error(
                "Translation failed — check internet connection or "
                "start LibreTranslate locally."
            )
            self.transcription_tray.set_translating(False)

    def check_translation_backends(self) -> None:
        """Fire an async availability check and log results (no UI update)."""
        asyncio.create_task(self._check_backends_async())

    async def _check_backends_async(self) -> None:
        availability = await self._translation_manager.check_availability()
        parts = ", ".join(
            f"{name}={'True' if ok else 'False'}"
            for name, ok in availability.items()
        )
        _logger.info("Translation backends: %s", parts)

    # --- SideMenu translation signal handlers ---

    def _on_translation_enabled_changed(self, enabled: bool) -> None:
        """Enable/disable the translate button in the tray."""
        self.transcription_tray._translate_btn.setEnabled(enabled)

    def _rebuild_translation_manager(self) -> None:
        """Rebuild the manager based on current backend setting."""
        backend_id = getattr(self, '_translation_backend', 'auto')
        url = self._libre_url
        if backend_id == "deepl":
            backends = [DeepLBackend()]
        elif backend_id == "google":
            backends = [GoogleTranslateBackend()]
        else:  # "auto"
            backends = [DeepLBackend(), GoogleTranslateBackend()]
        self._translation_manager = TranslationManager(backends)
        _logger.info(
            "[MainWindow] Translation manager rebuilt: backend=%s",
            backend_id,
        )

    def _on_translation_backend_changed(self, backend_id: str) -> None:
        """Rebuild manager with the selected backend(s)."""
        self._translation_backend = backend_id
        self._rebuild_translation_manager()

    def _on_libre_url_changed(self, url: str) -> None:
        """Store new URL and rebuild manager if libre is involved."""
        self._libre_url = url or "http://localhost:5000"
        backend_id = getattr(self, '_translation_backend', 'auto')
        if backend_id in ("auto", "libre"):
            self._rebuild_translation_manager()
