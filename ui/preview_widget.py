"""
QLabel-based live preview widget for the captured window feed.

Receives numpy BGR frames via a deque and renders them as QPixmap.
"""

import cv2
import numpy as np
from collections import deque
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap

from ui.selection_overlay import SelectionOverlay
from ui.theme import ThemePalette, DARK


class PreviewWidget(QWidget):
    """
    Widget that displays a live feed of the captured window.

    Wire it up:
        1. Create PreviewWidget instance
        2. Pass frame_queue (deque, maxlen=1) to it
        3. Async capture loop puts frames into the deque
        4. PreviewWidget's QTimer polls the deque at 50ms intervals
    """

    def __init__(self, frame_queue: deque, parent=None):
        super().__init__(parent)
        self._frame_queue = frame_queue
        self._last_frame: np.ndarray | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self._label = QLabel("No feed")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pal = None
        self._update_label_style()
        self._label.setMinimumSize(320, 180)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._label)

        # Overlay for click-and-drag region selection
        self._overlay = SelectionOverlay(self._get_frame_size, self)
        self._overlay.setGeometry(self._label.geometry())
        self._overlay.raise_()  # ensure overlay is painted on top

        # Timer: poll deque at 50ms (~20 fps)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_frame)
        self._timer.start(50)

    def _get_frame_size(self):
        """Return (width, height) of the last rendered frame, or (0, 0)."""
        if self._last_frame is not None:
            h, w = self._last_frame.shape[:2]
            return w, h
        return 0, 0

    @property
    def frame_size(self):
        """Return (width, height) of the last rendered frame, or (0, 0)."""
        return self._get_frame_size()

    @property
    def selection_overlay(self):
        return self._overlay

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, lambda: self._overlay.setGeometry(
            self._label.geometry()
        ))

    def _poll_frame(self):
        """Pop the latest frame from the deque and update display."""
        if not self._frame_queue:
            return

        frame = self._frame_queue.popleft()  # get latest, discard older
        self._last_frame = frame
        self._render_frame(frame)

    def _render_frame(self, frame: np.ndarray):
        """Convert numpy BGR -> QPixmap and display."""
        if frame is None or frame.size == 0:
            return

        h, w = frame.shape[:2]

        # BGR -> RGB conversion
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Build QImage from raw data -- hold bytes reference for lifetime
        rgb_bytes = rgb.tobytes()
        qimage = QImage(
            rgb_bytes, w, h,
            rgb.strides[0],
            QImage.Format.Format_RGB888,
        )

        pixmap = QPixmap.fromImage(qimage)

        # Scale to fit label while maintaining aspect ratio
        scaled = pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self._label.setPixmap(scaled)

    @property
    def latest_frame(self) -> np.ndarray | None:
        return self._last_frame

    def set_theme(self, pal: ThemePalette):
        self._pal = pal
        self._update_label_style()

    def _update_label_style(self):
        pal = self._pal
        bg = pal.panel if pal else "#1e1e1e"
        fg = pal.text_dim if pal else "#888888"
        self._label.setStyleSheet(
            f"background-color: {bg}; color: {fg}; font-size: 16px;"
        )

    def stop(self):
        """Stop the polling timer."""
        self._timer.stop()
