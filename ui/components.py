"""Reusable PyQt6 UI components: status bar."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from ui.theme import ThemePalette


class StatusBar(QStatusBar):
    """Bottom status bar showing app status and summary."""

    AUTO_CLEAR_MS = 2500  # "Done" / "Error" auto-revert to "Ready"
    STATUS_COLORS = {
        "Ready": None,  # falls through to text_dim below
        "Loading": "text_secondary",
        "Processing": "warn",
        "Done": "accent",
        "Error": "panic",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)

        # --- Line 1: status text (large, bold, color-coded) ---
        self._status_label = QLabel("Ready")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        layout.addWidget(self._status_label)

        # --- Line 2: config summary (small, dim) ---
        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._summary_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        layout.addWidget(self._summary_label)

        # Fix the container height so the status bar never shrinks/expands
        # and pushes the transcription tray above it.
        line_spacing = self._status_label.fontMetrics().lineSpacing()
        summary_spacing = self._summary_label.fontMetrics().lineSpacing()
        container.setMinimumHeight(int(line_spacing * 1.2 + summary_spacing * 1.2 + 4))

        container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.addPermanentWidget(container, 1)

        # Theme state
        self._pal: ThemePalette | None = None
        self._current_status_key: str = "Ready"

        # Auto-clear timer
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self._on_clear_timeout)

    # ── theme ──────────────────────────────────────────────

    def set_theme(self, pal: ThemePalette):
        self._pal = pal
        # Re-compute colour for the current status key now that palette is known
        self._current_status_color = self._color_for_status(self._current_status_key)
        self._apply_current_style()

    def _color_for_status(self, status_key: str) -> str:
        """Return hex colour for a status key, falling back to text_dim."""
        if self._pal is None:
            return "#ccc"
        color_attr = self.STATUS_COLORS.get(status_key)
        if color_attr is None:
            return self._pal.text_dim
        return getattr(self._pal, color_attr, self._pal.text_dim)

    def _apply_current_style(self) -> None:
        """Re-apply stylesheet to both labels from current theme."""
        if self._pal is None:
            return
        dim = self._pal.text_dim
        self._status_label.setStyleSheet(
            f"color: {self._current_status_color}; font-size: 14px; font-weight: 600;"
        )
        self._summary_label.setStyleSheet(
            f"color: {dim}; font-size: 11px;"
        )

    # ── public API ─────────────────────────────────────────

    def set_status(self, status_text: str, summary_text: str):
        # Determine colour key
        for key in self.STATUS_COLORS:
            if status_text.startswith(key):
                status_key = key
                break
        else:
            status_key = "Ready"

        # Persist current key so set_theme() can re-compute colour after palette loads
        self._current_status_key = status_key

        # Store colour for _apply_current_style
        self._current_status_color = self._color_for_status(status_key)

        # Style and set text
        self._apply_current_style()
        self._status_label.setText(status_text)
        self._summary_label.setText(summary_text)

        # Auto-clear transient states
        if status_key in ("Done", "Error"):
            self._clear_timer.start(self.AUTO_CLEAR_MS)
        else:
            self._clear_timer.stop()

    def _on_clear_timeout(self):
        """Revert to Ready after timeout."""
        self._current_status_key = "Ready"
        self._current_status_color = self._color_for_status("Ready")
        self._apply_current_style()
        self._status_label.setText("Ready")
        self._summary_label.setText("")
