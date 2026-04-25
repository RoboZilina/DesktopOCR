"""Reusable PyQt6 UI components: status bar."""

from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QVBoxLayout, QStatusBar, QWidget,
)
from ui.theme import ThemePalette


class StatusBar(QStatusBar):
    """Bottom status bar showing engine, FPS, window info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(8, 4, 8, 4)

        self._engine_label = QLabel("Engine: \u2014")
        self._fps_label = QLabel("FPS: \u2014")
        self._conf_label = QLabel("Conf: \u2014")
        self._window_label = QLabel("Window: \u2014")

        for lbl in (self._engine_label, self._fps_label,
                     self._conf_label, self._window_label):
            lbl.setStyleSheet("color: #ccc; font-size: 12px;")
            layout.addWidget(lbl)

        layout.addStretch()
        self.addWidget(container, 1)

    def set_theme(self, pal: ThemePalette):
        color = pal.text_dim if pal else "#ccc"
        for lbl in (self._engine_label, self._fps_label,
                     self._conf_label, self._window_label):
            lbl.setStyleSheet(f"color: {color}; font-size: 12px;")

    def set_engine(self, name: str):
        self._engine_label.setText(f"Engine: {name}")

    def set_fps(self, fps: float):
        self._fps_label.setText(f"FPS: {fps:.1f}")

    def set_confidence(self, conf: float):
        self._conf_label.setText(f"Conf: {conf:.2f}")

    def set_window_title(self, title: str):
        self._window_label.setText(f"Window: {title}")
