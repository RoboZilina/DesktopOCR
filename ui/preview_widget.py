"""
QLabel-based live preview widget for the captured window feed.

Receives numpy BGR frames via a deque and renders them as QPixmap.
"""

import cv2
import numpy as np
from collections import deque
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QSizePolicy, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor

from ui.selection_overlay import SelectionOverlay
from ui.theme import ThemePalette, DARK


class _BoxOverlay(QWidget):
    def __init__(self, frame_size_cb, parent=None):
        super().__init__(parent)
        self._get_frame_size = frame_size_cb
        self._boxes: list[tuple[float, float, float, float]] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_boxes(self, boxes: list | None):
        sanitized: list[tuple[float, float, float, float]] = []
        if boxes:
            for box in boxes:
                if not isinstance(box, (list, tuple)) or len(box) < 4:
                    continue
                try:
                    x1 = float(box[0])
                    y1 = float(box[1])
                    x2 = float(box[2])
                    y2 = float(box[3])
                except (TypeError, ValueError):
                    continue
                sanitized.append((x1, y1, x2, y2))
        self._boxes = sanitized
        self.update()

    def clear_boxes(self):
        if self._boxes:
            self._boxes = []
            self.update()

    def _get_transform(self):
        imgW, imgH = self._get_frame_size()
        if imgW <= 0 or imgH <= 0:
            return None
        ow, oh = self.width(), self.height()
        if ow <= 0 or oh <= 0:
            return None
        scale = min(ow / imgW, oh / imgH)
        dispW = imgW * scale
        dispH = imgH * scale
        offsetX = (ow - dispW) / 2.0
        offsetY = (oh - dispH) / 2.0
        return scale, offsetX, offsetY

    def paintEvent(self, event):
        if not self._boxes:
            return
        transform = self._get_transform()
        if not transform:
            return
        scale, offsetX, offsetY = transform
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(255, 92, 92))
        pen.setWidth(2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for x1, y1, x2, y2 in self._boxes:
            rx1 = x1 * scale + offsetX
            ry1 = y1 * scale + offsetY
            rx2 = x2 * scale + offsetX
            ry2 = y2 * scale + offsetY
            rect = QRectF(QPointF(rx1, ry1), QPointF(rx2, ry2)).normalized()
            painter.drawRect(rect)
        painter.end()


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
        self._boxes_overlay: _BoxOverlay | None = None

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

        self._hint_message = (
            "Click and drag on the preview to select a text region. "
            "Keep the selection tight around the text to prevent ghost characters."
        )
        self._hint_label = QLabel(self._hint_message)
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setWordWrap(True)
        self._hint_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._hint_label.setMinimumHeight(32)
        self._hint_dismissed = False
        layout.addWidget(self._hint_label)

        # Detection boxes overlay (non-interactive)
        self._boxes_overlay = _BoxOverlay(self._get_frame_size, self)
        self._boxes_overlay.setGeometry(self._label.geometry())

        # Overlay for click-and-drag region selection (interactive, sits on top)
        self._overlay = SelectionOverlay(self._get_frame_size, self)
        self._overlay.setGeometry(self._label.geometry())
        self._overlay.raise_()  # ensure overlay is painted on top
        self._overlay.region_changed.connect(self._on_selection_changed)
        if self._boxes_overlay is not None:
            self._boxes_overlay.stackUnder(self._overlay)
        self._overlay.set_line_band_count(1)

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
        def _sync_overlays():
            geom = self._label.geometry()
            self._overlay.setGeometry(geom)
            if self._boxes_overlay is not None:
                self._boxes_overlay.setGeometry(geom)
        QTimer.singleShot(0, _sync_overlays)

    def _poll_frame(self):
        """Pop the latest frame from the deque and update display."""
        if not self._frame_queue:
            return

        frame = self._frame_queue.popleft()  # get latest, discard older
        self._last_frame = frame
        self._render_frame(frame)
        if self._boxes_overlay is not None:
            self._boxes_overlay.update()

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

    # ------------------------------------------------------------------
    # OCR Detection Overlay API
    # ------------------------------------------------------------------

    def set_ocr_boxes(self, boxes: list | None):
        if self._boxes_overlay is None:
            return
        self._boxes_overlay.set_boxes(boxes)

    def clear_ocr_boxes(self):
        if self._boxes_overlay is None:
            return
        self._boxes_overlay.clear_boxes()

    def set_line_guides(self, count: int):
        if hasattr(self, "_overlay") and self._overlay is not None:
            self._overlay.set_line_band_count(max(1, int(count or 1)))

    def clear_frame(self, placeholder: str | None = None, *, clear_selection: bool = False):
        """Reset the preview to a placeholder message and optionally clear selection."""
        self._last_frame = None
        self._label.clear()
        self._label.setText(placeholder or "No feed")
        self.clear_ocr_boxes()
        if clear_selection and hasattr(self._overlay, "clear_selection"):
            self._overlay.clear_selection()

    def set_theme(self, pal: ThemePalette):
        self._pal = pal
        self._update_label_style()
        self._update_hint_style()

    def _update_label_style(self):
        pal = self._pal
        bg = pal.panel if pal else "#1e1e1e"
        fg = pal.text_dim if pal else "#888888"
        self._label.setStyleSheet(
            f"background-color: {bg}; color: {fg}; font-size: 16px;"
        )

    def _on_selection_changed(self, nx: float, ny: float, nw: float, nh: float) -> None:
        imgW, imgH = self._get_frame_size()
        if imgW == 0 or imgH == 0:
            return

        w_px = nw * imgW
        h_px = nh * imgH

        if w_px < 20 or h_px < 20:
            self._hint_dismissed = False  # ensure message is visible again
            self._hint_label.setText("Selected area is too small (min 20×20).")
            self._update_hint_style()
            return

        if nw > 0 and nh > 0:
            self._dismiss_hint()

    def _update_hint_style(self):
        pal = self._pal
        fg = "transparent" if self._hint_dismissed else (pal.text_dim if pal else "#888888")
        bg = "rgba(8, 8, 12, 0.45)" if pal and pal.is_dark else "rgba(240, 244, 255, 0.65)"
        border = pal.border if pal else "#2a2a30"
        self._hint_label.setStyleSheet(
            f"color: {fg}; font-size: 12px; padding: 6px 10px; "
            f"border: 1px dashed {border}; border-radius: 8px; background: {bg};"
        )
        if not self._hint_dismissed and not self._hint_label.text():
            self._hint_label.setText(self._hint_message)
        elif self._hint_dismissed:
            self._hint_label.clear()

    def _dismiss_hint(self):
        if self._hint_dismissed:
            return
        self._hint_dismissed = True
        self._hint_label.clear()
        self._update_hint_style()

    def stop(self):
        """Stop the polling timer."""
        self._timer.stop()


class OcrCanvasWidget(QWidget):
    """Displays the actual OCR input frame plus detection boxes for debugging."""

    MODE_RAW = "raw"
    MODE_PROCESSED = "processed"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_frame: np.ndarray | None = None
        self._raw_frame: np.ndarray | None = None
        self._processed_frame: np.ndarray | None = None
        self._display_mode: str = self.MODE_PROCESSED
        self._pal: ThemePalette | None = None
        self._subtitle_default = "Shows the cropped + preprocessed frame exactly as it feeds Paddle."

        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 12, 0, 0)
        wrapper.setSpacing(2)

        self._title = QLabel("OCR Canvas (engine input)")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._title.setStyleSheet("font-weight: 600;")
        wrapper.addWidget(self._title)

        self._subtitle = QLabel(self._subtitle_default)
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet("font-size: 11px; margin-bottom: 4px;")
        wrapper.addWidget(self._subtitle)

        controls = QHBoxLayout()
        controls.setContentsMargins(4, 0, 4, 4)
        controls.setSpacing(6)
        self._raw_btn = QPushButton("Raw crop")
        self._raw_btn.setCheckable(True)
        self._raw_btn.clicked.connect(lambda _: self._set_display_mode(self.MODE_RAW))
        self._processed_btn = QPushButton("Paddle input")
        self._processed_btn.setCheckable(True)
        self._processed_btn.clicked.connect(lambda _: self._set_display_mode(self.MODE_PROCESSED))
        controls.addWidget(self._raw_btn)
        controls.addWidget(self._processed_btn)
        controls.addStretch(1)
        wrapper.addLayout(controls)

        self._image_label = QLabel("No OCR capture yet")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumHeight(200)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        wrapper.addWidget(self._image_label, stretch=1)

        self._boxes_overlay = _BoxOverlay(self._get_frame_size, self)
        self._boxes_overlay.setGeometry(self._image_label.geometry())
        self._update_mode_buttons()

    def _get_frame_size(self):
        if self._last_frame is not None:
            h, w = self._last_frame.shape[:2]
            return w, h
        return 0, 0

    def resizeEvent(self, event):
        super().resizeEvent(event)

        def _sync_overlay():
            geom = self._image_label.geometry()
            self._boxes_overlay.setGeometry(geom)

        QTimer.singleShot(0, _sync_overlay)

    def set_canvas_frames(
        self,
        raw_frame: np.ndarray | None,
        processed_frame: np.ndarray | None,
        boxes: list | None = None,
    ):
        self._raw_frame = raw_frame.copy() if isinstance(raw_frame, np.ndarray) and raw_frame.size > 0 else None
        self._processed_frame = (
            processed_frame.copy() if isinstance(processed_frame, np.ndarray) and processed_frame.size > 0 else None
        )
        self._update_mode_buttons()
        self._refresh_canvas(boxes)

    def set_canvas_frame(self, frame: np.ndarray | None, boxes: list | None = None):
        """Backward-compatible helper when only one frame variant is available."""
        self.set_canvas_frames(frame, frame, boxes)

    def set_ocr_boxes(self, boxes: list | None):
        self._boxes_overlay.set_boxes(boxes)

    def clear_canvas(self):
        self._last_frame = None
        self._raw_frame = None
        self._processed_frame = None
        self._image_label.clear()
        self._image_label.setText("No OCR capture yet")
        self._boxes_overlay.clear_boxes()
        if self._subtitle is not None:
            self._subtitle.setText(self._subtitle_default)
        self._update_mode_buttons()

    def _render_frame(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_bytes = rgb.tobytes()
        qimage = QImage(
            rgb_bytes,
            w,
            h,
            rgb.strides[0],
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(qimage)
        scaled = pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        self._image_label.setText("")
        self._boxes_overlay.update()

    def set_theme(self, pal: ThemePalette):
        self._pal = pal
        fg = pal.text if pal else "#ffffff"
        dim = pal.text_dim if pal else "#cccccc"
        bg = pal.panel if pal else "#101013"
        border = pal.border if pal else "#1f1f23"
        accent = pal.accent if pal else "#3b82f6"
        self.setStyleSheet(f"background: {bg}; border-top: 1px solid {border};")
        self._title.setStyleSheet(
            f"color: {fg}; font-size: 13px; font-weight: 600; padding-left: 4px;"
        )
        self._subtitle.setStyleSheet(
            f"color: {dim}; font-size: 11px; padding-left: 4px; margin-bottom: 4px;"
        )
        self._image_label.setStyleSheet(
            f"background: rgba(0,0,0,0.25); color: {dim}; border: 1px dashed {border};"
        )
        btn_style = (
            "QPushButton {{ padding: 4px 10px; border-radius: 6px; border: 1px solid {border}; "
            "color: {dim}; background: transparent; }} "
            "QPushButton:checked {{ color: #ffffff; background: {accent}; border-color: {accent}; }} "
            "QPushButton:disabled {{ color: rgba(255,255,255,0.35); border-color: rgba(255,255,255,0.15); }}"
        ).format(border=border, dim=dim, accent=accent)
        self._raw_btn.setStyleSheet(btn_style)
        self._processed_btn.setStyleSheet(btn_style)

    # ---- Internal helpers -------------------------------------------------

    def _set_display_mode(self, mode: str):
        if mode not in (self.MODE_RAW, self.MODE_PROCESSED):
            return
        if self._display_mode == mode:
            return
        self._display_mode = mode
        self._update_mode_buttons()
        self._refresh_canvas()

    def _update_mode_buttons(self):
        has_raw = self._raw_frame is not None
        has_processed = self._processed_frame is not None
        if not has_processed and has_raw:
            self._display_mode = self.MODE_RAW
        elif not has_raw and has_processed:
            self._display_mode = self.MODE_PROCESSED
        elif not has_raw and not has_processed:
            self._display_mode = self.MODE_PROCESSED

        self._raw_btn.setEnabled(has_raw)
        self._processed_btn.setEnabled(has_processed)
        self._raw_btn.setChecked(self._display_mode == self.MODE_RAW)
        self._processed_btn.setChecked(self._display_mode == self.MODE_PROCESSED)

    def _get_active_frame(self) -> np.ndarray | None:
        if self._display_mode == self.MODE_RAW:
            return self._raw_frame if self._raw_frame is not None else self._processed_frame
        return self._processed_frame if self._processed_frame is not None else self._raw_frame

    def _refresh_canvas(self, boxes: list | None = None):
        frame = self._get_active_frame()
        if frame is None or frame.size == 0:
            self.clear_canvas()
            return

        self._last_frame = frame.copy()
        self._render_frame(self._last_frame)
        if boxes is not None:
            self._boxes_overlay.set_boxes(boxes)
        label = "Raw crop" if self._display_mode == self.MODE_RAW else "Engine input (post-processed)"
        h, w = self._last_frame.shape[:2]
        self._subtitle.setText(f"{label} {w}×{h}px")
        self._boxes_overlay.update()
