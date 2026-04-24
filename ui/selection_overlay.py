"""
Transparent overlay widget for click-and-drag region selection on the preview.

Draws a semi-transparent selection rectangle with border and corner accents.
Coordinates are mapped from overlay pixels through aspect-fit letterboxing to
normalized [0,1] space relative to the original capture frame.
"""

from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush


class SelectionOverlay(QWidget):
    region_changed = pyqtSignal(float, float, float, float)  # nx, ny, nw, nh (normalized)

    MIN_SEL_PX = 8  # minimum selection size in original frame pixels

    def __init__(self, get_frame_size_callback, parent=None):
        super().__init__(parent)
        self._get_frame_size = get_frame_size_callback

        self._start_overlay: QPointF | None = None
        self._current_overlay: QPointF | None = None
        self._selection_norm: tuple[float, float, float, float] | None = None
        self._last_valid_norm: tuple[float, float, float, float] | None = None
        self._dragging = False

        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAutoFillBackground(False)

    # ------------------------------------------------------------------
    # Coordinate transform: overlay pixels <-> normalized [0,1]
    # ------------------------------------------------------------------

    def _get_transform(self) -> tuple[float, float, float, float, float] | None:
        imgW, imgH = self._get_frame_size()
        if imgW == 0 or imgH == 0:
            return None
        ow, oh = self.width(), self.height()
        scale = min(ow / imgW, oh / imgH)
        dispW = imgW * scale
        dispH = imgH * scale
        offsetX = (ow - dispW) / 2.0
        offsetY = (oh - dispH) / 2.0
        return scale, offsetX, offsetY, imgW, imgH

    def _overlay_to_norm(self, mx: float, my: float) -> tuple[float, float] | None:
        t = self._get_transform()
        if t is None:
            return None
        scale, offsetX, offsetY, imgW, imgH = t
        ix = (mx - offsetX) / scale
        iy = (my - offsetY) / scale
        nx = max(0.0, min(1.0, ix / imgW))
        ny = max(0.0, min(1.0, iy / imgH))
        return nx, ny

    def _norm_to_overlay(self, nx: float, ny: float) -> tuple[float, float] | None:
        t = self._get_transform()
        if t is None:
            return None, None
        scale, offsetX, offsetY, imgW, imgH = t
        mx = nx * imgW * scale + offsetX
        my = ny * imgH * scale + offsetY
        return mx, my

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_overlay = QPointF(event.position())
            self._current_overlay = QPointF(event.position())
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._current_overlay = QPointF(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._current_overlay = QPointF(event.position())

            start_n = self._overlay_to_norm(
                self._start_overlay.x(), self._start_overlay.y()
            )
            end_n = self._overlay_to_norm(
                self._current_overlay.x(), self._current_overlay.y()
            )
            if start_n is None or end_n is None:
                return

            nx1, ny1 = start_n
            nx2, ny2 = end_n
            nx = min(nx1, nx2)
            ny = min(ny1, ny2)
            nw = abs(nx2 - nx1)
            nh = abs(ny2 - ny1)

            # Validate minimum size in original frame pixels
            imgW, imgH = self._get_frame_size()
            pw = nw * imgW
            ph = nh * imgH
            if pw >= self.MIN_SEL_PX and ph >= self.MIN_SEL_PX:
                self._selection_norm = (nx, ny, nw, nh)
                self._last_valid_norm = (nx, ny, nw, nh)
                self.region_changed.emit(nx, ny, nw, nh)
            else:
                # Reject tiny drag; restore previous valid selection
                self._selection_norm = self._last_valid_norm
                if self._last_valid_norm:
                    self.region_changed.emit(*self._last_valid_norm)

            self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)

        if self._dragging and self._start_overlay and self._current_overlay:
            self._draw_rect(painter, self._start_overlay, self._current_overlay)
        elif self._selection_norm:
            nx, ny, nw, nh = self._selection_norm
            x1, y1 = self._norm_to_overlay(nx, ny)
            x2, y2 = self._norm_to_overlay(nx + nw, ny + nh)
            if x1 is not None and y1 is not None:
                self._draw_rect(painter, QPointF(x1, y1), QPointF(x2, y2))

        painter.end()

    def _draw_rect(self, painter: QPainter, p1: QPointF, p2: QPointF):
        rect = QRectF(p1, p2).normalized()

        # Semi-transparent fill
        painter.fillRect(rect, QColor(0, 120, 255, 64))

        # White border
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawRect(rect)

        # Corner accent squares
        accent = 8.0
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRect(QRectF(rect.left(), rect.top(), accent, accent))
        painter.drawRect(QRectF(rect.right() - accent, rect.top(), accent, accent))
        painter.drawRect(QRectF(rect.left(), rect.bottom() - accent, accent, accent))
        painter.drawRect(QRectF(rect.right() - accent, rect.bottom() - accent, accent, accent))

    # ------------------------------------------------------------------
    # External API
    # ------------------------------------------------------------------

    def set_selection(self, nx: float, ny: float, nw: float, nh: float):
        """Restore a selection from external source (e.g., saved settings)."""
        self._selection_norm = (nx, ny, nw, nh)
        self._last_valid_norm = (nx, ny, nw, nh)
        self.update()
