"""Main application window — assembles all UI components."""

import asyncio
import logging
from collections import deque
import numpy as np

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QGuiApplication
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
    select_window_requested = pyqtSignal()
    stop_stream_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DesktopOCR")
        self.setMinimumSize(900, 600)
        self.resize(1100, 680)

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
        self.controls_bar.select_window_requested.connect(self.select_window_requested.emit)
        self.controls_bar.stop_stream_requested.connect(self.stop_stream_requested.emit)
        self.transcription_tray.recapture_requested.connect(self.recapture_requested.emit)
        self.transcription_tray.tts_requested.connect(self.tts_requested.emit)
        self.transcription_tray.selection_changed.connect(self._on_selection_text_changed)
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
        self._auto_read_selection = False
        self._auto_translate_selection = False
        self._translation_enabled = True
        self._selection_delay_timer = QTimer(self)
        self._selection_delay_timer.setSingleShot(True)
        self._selection_delay_timer.timeout.connect(self._on_selection_action_due)
        self._pending_selection_text: str = ""

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
        self.side_menu.auto_read_selection_changed.connect(
            self._on_auto_read_selection_changed
        )
        self.side_menu.auto_translate_selection_changed.connect(
            self._on_auto_translate_selection_changed
        )

        # Detect and apply system theme on startup
        self._detect_and_apply_theme()

        # Auto-fit preview sizing
        self._pending_auto_fit = True

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
        if frame is None:
            self.clear_preview()
            return
        self._frame_queue.append(frame.copy())
        self._auto_fit_preview_to_frame(frame.shape[1], frame.shape[0])

    def clear_preview(self, placeholder: str | None = None, *, clear_selection: bool = False):
        """Remove any queued frames and show a placeholder in the preview widget."""
        self._frame_queue.clear()
        self.preview_widget.clear_frame(placeholder, clear_selection=clear_selection)

    def set_status(self, engine: str, fps: float, conf: float, window_title: str):
        self.status_bar.set_engine(engine)
        self.status_bar.set_fps(fps)
        self.status_bar.set_confidence(conf)
        self.status_bar.set_window_title(window_title)

    def request_preview_auto_fit(self) -> None:
        """Allow the next incoming frame to resize the window to match its width."""
        self._pending_auto_fit = True

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

    async def _dispose_translation_manager(self, manager) -> None:
        """Dispose all backends in a translation manager."""
        if manager is None:
            return
        backends = getattr(manager, "_backends", {})
        for backend in backends.values() if isinstance(backends, dict) else []:
            if hasattr(backend, "dispose"):
                try:
                    await backend.dispose()
                except Exception:  # noqa: BLE001
                    pass

    def _on_translation_enabled_changed(self, enabled: bool) -> None:
        """Enable/disable the translate button in the tray."""
        self._translation_enabled = enabled
        self.transcription_tray._translate_btn.setEnabled(enabled)

    def _rebuild_translation_manager(self) -> None:
        """Rebuild the manager based on current backend setting."""
        old_manager = getattr(self, '_translation_manager', None)
        if old_manager is not None:
            asyncio.create_task(self._dispose_translation_manager(old_manager))
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

    def _on_auto_read_selection_changed(self, enabled: bool) -> None:
        self._auto_read_selection = bool(enabled)

    def _on_auto_translate_selection_changed(self, enabled: bool) -> None:
        self._auto_translate_selection = bool(enabled)

    def _on_selection_text_changed(self, text: str) -> None:
        text = (text or "").strip()
        self._pending_selection_text = text
        if not text:
            self._selection_delay_timer.stop()
            return
        self._selection_delay_timer.start(1000)

    def _on_selection_action_due(self) -> None:
        text = (self._pending_selection_text or "").strip()
        if not text:
            return
        if self._auto_read_selection:
            self.tts_requested.emit(text)
        if self._auto_translate_selection and self._translation_enabled:
            self.translate_requested.emit(text)

    # --- Preview sizing helpers ---

    def _auto_fit_preview_to_frame(self, frame_w: int, frame_h: int) -> None:
        if not self._pending_auto_fit:
            return
        if frame_w <= 0 or frame_h <= 0:
            return

        sidebar_width = max(
            self.history_sidebar.width(),
            self.history_sidebar.sizeHint().width(),
            320,
        )
        menu_h = self.menuWidget().height() if self.menuWidget() else 48
        tray_hint = self.transcription_tray.sizeHint().height()
        status_h = self.status_bar.height() if self.status_bar else 24

        left_column_width = max(
            self.preview_widget.width(),
            self.transcription_tray.width(),
            self.preview_widget.sizeHint().width(),
            760,
        )

        preview_scale = left_column_width / frame_w if frame_w > 0 else 1.0
        preview_height = frame_h * preview_scale
        target_height = preview_height + tray_hint + menu_h + status_h

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            target_height = min(target_height, max(avail.height() - 40, 600))

        target_height = max(target_height, 600)

        self.resize(self.width(), int(target_height))
        self._pending_auto_fit = False
