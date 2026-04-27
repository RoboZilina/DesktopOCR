"""Reusable PyQt6 UI components: status bar."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStatusBar,
    QWidget,
)
from ui.theme import ThemePalette


class StatusBar(QStatusBar):
    """Bottom status bar showing app status and summary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        self._status_label = QLabel("Ready")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        line_spacing = self._status_label.fontMetrics().lineSpacing()
        self._status_label.setMinimumHeight(int(line_spacing * 2.2))
        layout.addWidget(self._status_label)

        self.addPermanentWidget(container, 1)

    def set_theme(self, pal: ThemePalette):
        color = pal.text_dim if pal else "#ccc"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def set_status(self, status_text: str, summary_text: str):
        if summary_text:
            self._status_label.setText(f"{status_text}\n{summary_text}")
        else:
            self._status_label.setText(status_text)
