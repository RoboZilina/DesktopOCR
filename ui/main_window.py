"""Main application window — assembles all UI components."""

import asyncio
import logging
import pathlib
from collections import deque
import numpy as np

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from ui.theme import DARK, LIGHT, ThemePalette, apply_theme
from ui.controls_bar import ControlsBar
from ui.preview_widget import PreviewWidget, OcrCanvasWidget
from ui.transcription_tray import TranscriptionTray
from ui.history_sidebar import HistorySidebar
from ui.side_menu import SideMenu
from ui.components import StatusBar
from ui.user_guide_dialog import UserGuideDialog
from core.translation.manager import TranslationManager
from core.translation.deepl_backend import DeepLBackend
from core.translation.google_backend import GoogleTranslateBackend

_logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    engine_changed = pyqtSignal(str)
    paddle_line_count_changed = pyqtSignal(int)
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
        self.setWindowFlags(Qt.WindowType.Window)

        # Frame queue for preview widget
        self._frame_queue = deque(maxlen=1)
        self._active_engine_id = "paddle"
        self._paddle_line_count = 3

        # Controls bar (top)
        paddle_variants = [f"paddle-{i}" for i in range(1, 6)]
        engine_options = paddle_variants + ["windows_ocr"]
        self.controls_bar = ControlsBar(engine_options)
        self.controls_bar.set_engine(f"paddle-{self._paddle_line_count}")
        self._top_container = QWidget()
        top_layout = QHBoxLayout(self._top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addWidget(self.controls_bar, 1)


        self.setMenuWidget(self._top_container)
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
        self.ocr_canvas = OcrCanvasWidget()
        self.ocr_canvas.setVisible(False)
        self.transcription_tray = TranscriptionTray()
        self.preview_widget.set_line_guides(self.get_active_line_count())

        left_layout.addWidget(self.preview_widget, stretch=1)
        left_layout.addWidget(self.ocr_canvas, stretch=0)
        left_layout.addWidget(self.transcription_tray)

        main_layout.addWidget(left_widget, stretch=1)

        # Right column
        self.history_sidebar = HistorySidebar()
        main_layout.addWidget(self.history_sidebar)

        # Status bar (native)
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.set_status("Ready", "")

        # Side menu overlay (hidden by default)
        self.side_menu = SideMenu(self)
        self.side_menu.setVisible(False)
        self._menu_overlay = QWidget(self)
        self._menu_overlay.setObjectName("SideMenuOverlay")
        self._menu_overlay.setStyleSheet("background: rgba(0, 0, 0, 0);")
        self._menu_overlay.hide()
        self._menu_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        def _overlay_click(event):  # noqa: ANN001
            self._hide_side_menu()

        self._menu_overlay.mousePressEvent = _overlay_click

        # Wire internal signals to MainWindow signals
        self.controls_bar.menu_requested.connect(self._toggle_side_menu)
        self.controls_bar.engine_changed.connect(self._handle_engine_selection)
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
        self.side_menu.hide_requested.connect(self._hide_side_menu)

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
        self.side_menu.ocr_canvas_visible_changed.connect(
            self._on_ocr_canvas_visible_changed
        )
        self.side_menu.user_guide_requested.connect(self._show_user_guide)

        self._user_guide_path = pathlib.Path("docs/user_guide.html")

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
        self.ocr_canvas.set_theme(pal)

    def _show_user_guide(self):
        dialog = UserGuideDialog(self, guide_path=str(self._user_guide_path))
        dialog.exec()

    def _on_ocr_canvas_visible_changed(self, visible: bool) -> None:
        self.ocr_canvas.setVisible(visible)

    # --- Side menu positioning ---

    def _toggle_side_menu(self):
        if self.side_menu.isVisible():
            self._hide_side_menu()
        else:
            self._show_side_menu()

    def _show_side_menu(self):
        self.side_menu.setVisible(True)
        self._position_side_menu()
        self._menu_overlay.setGeometry(*self._overlay_geometry())
        self._menu_overlay.setStyleSheet("background: rgba(0, 0, 0, 40);")
        self._menu_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._menu_overlay.show()
        self._menu_overlay.raise_()
        self.side_menu.raise_()
        if hasattr(self.controls_bar, "set_menu_icon"):
            self.controls_bar.set_menu_icon(True)

    def _hide_side_menu(self):
        if not self.side_menu.isVisible():
            return
        self.side_menu.setVisible(False)
        self._menu_overlay.hide()
        self._menu_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if hasattr(self.controls_bar, "set_menu_icon"):
            self.controls_bar.set_menu_icon(False)

    def _position_side_menu(self):
        if self._menu_overlay:
            self._menu_overlay.setGeometry(*self._overlay_geometry())
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

    def _overlay_geometry(self):
        bar_height = self.menuWidget().height() if self.menuWidget() else 0
        return 0, bar_height, self.width(), self.height() - bar_height

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

    def set_ocr_boxes(self, boxes: list | None):
        # Only the dedicated OCR canvas should visualize detection boxes.
        # Keep the live preview clean for capture framing.
        self.preview_widget.clear_ocr_boxes()
        self.ocr_canvas.set_ocr_boxes(boxes)

    def set_ocr_canvas_frames(
        self,
        raw_frame: np.ndarray | None,
        processed_frame: np.ndarray | None,
        boxes: list | None = None,
    ):
        self.ocr_canvas.set_canvas_frames(raw_frame, processed_frame, boxes)

    def set_ocr_canvas_frame(self, frame: np.ndarray | None, boxes: list | None = None):
        # Back-compat shim
        self.set_ocr_canvas_frames(frame, frame, boxes)

    def clear_preview(self, placeholder: str | None = None, *, clear_selection: bool = False):
        """Remove any queued frames and show a placeholder in the preview widget."""
        self._frame_queue.clear()
        self.preview_widget.clear_frame(placeholder, clear_selection=clear_selection)
        self.ocr_canvas.clear_canvas()

    def set_status(self, status_text: str, summary_text: str):
        self.status_bar.set_status(status_text, summary_text)

    def get_translator_summary(self) -> str:
        backend = getattr(self, "_translation_backend", "auto") or "auto"
        label_map = {
            "auto": "Auto",
            "deepl": "DeepL",
            "google": "Google",
        }
        label = label_map.get(backend, backend.title())
        return label if self._translation_enabled else f"{label} (off)"

    # --- Engine selection helpers ---

    def get_active_engine_id(self) -> str:
        return self._active_engine_id

    def get_active_line_count(self) -> int:
        if self._active_engine_id == "paddle":
            return max(1, int(self._paddle_line_count or 3))
        return 1

    def set_active_engine(self, engine_id: str, line_count: int | None = None) -> None:
        selection = self._format_engine_choice(engine_id, line_count)
        self.controls_bar.set_engine(selection)
        self._apply_engine_selection(selection, emit_signal=False)

    def _handle_engine_selection(self, selection: str) -> None:  # pragma: no cover - Qt slot
        self._apply_engine_selection(selection, emit_signal=True)

    def _apply_engine_selection(self, selection: str, *, emit_signal: bool) -> None:
        base_engine, line_count = self._parse_engine_choice(selection)
        previous_engine = self._active_engine_id
        prev_line_count = self._paddle_line_count
        self._active_engine_id = base_engine

        if base_engine == "paddle":
            new_line_count = max(1, min(5, line_count))
        else:
            new_line_count = 1
        self._paddle_line_count = new_line_count
        line_changed = new_line_count != prev_line_count

        if hasattr(self, "preview_widget"):
            self.preview_widget.set_line_guides(self.get_active_line_count())

        if line_changed:
            self.paddle_line_count_changed.emit(self._paddle_line_count)

        if emit_signal and previous_engine != base_engine:
            self.engine_changed.emit(base_engine)

    def _parse_engine_choice(self, selection: str) -> tuple[str, int]:
        if not selection:
            return "paddle", 3
        selection = selection.strip().lower()
        if selection.startswith("paddle"):
            parts = selection.split("-", 1)
            line_count = 3
            if len(parts) == 2:
                try:
                    line_count = int(parts[1])
                except ValueError:
                    line_count = 3
            return "paddle", max(1, min(5, line_count))
        return selection, 1

    def _format_engine_choice(self, engine_id: str, line_count: int | None) -> str:
        if engine_id == "paddle":
            normalized = line_count if line_count is not None else self.get_active_line_count()
            normalized = max(1, min(5, int(normalized)))
            return f"paddle-{normalized}"
        return engine_id

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
