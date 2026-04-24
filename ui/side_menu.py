"""Slide-in side menu panel — mirrors web app's #side-menu."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal


class SideMenu(QWidget):
    """Right-edge overlay panel with toggle sections and action buttons."""

    auto_capture_changed     = pyqtSignal(bool)
    auto_copy_changed        = pyqtSignal(bool)
    history_visible_changed  = pyqtSignal(bool)
    preview_visible_changed  = pyqtSignal(bool)
    vn_cleaner_changed       = pyqtSignal(bool)
    diff_threshold_changed   = pyqtSignal(float)
    reset_requested          = pyqtSignal()
    unload_engines_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self.setObjectName("SideMenu")
        self.setStyleSheet(
            """
            #SideMenu {
                background: #1a1a2e;
                border-left: 1px solid #333;
            }
            QLabel { color: #aaa; font-size: 11px; font-weight: bold; }
            QPushButton.option-btn {
                background: #2a2a3e;
                color: #ccc;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton.option-btn:checked {
                background: #2a4a7a;
                color: white;
                border-color: #4a8aff;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QLabel("Settings")
        header.setStyleSheet("color: #fff; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)
        layout.addWidget(self._divider())

        # Toggle sections
        self._add_toggle_section(layout, "Auto-Capture",
                                 self.auto_capture_changed, default=True)
        self._add_toggle_section(layout, "Auto-Copy",
                                 self.auto_copy_changed, default=False)
        self._add_toggle_section(layout, "History Panel",
                                 self.history_visible_changed, default=True)
        self._add_toggle_section(layout, "Capture Preview",
                                 self.preview_visible_changed, default=True)
        self._add_toggle_section(layout, "VN Text Cleaner",
                                 self.vn_cleaner_changed, default=True)

        # Diff threshold slider
        layout.addWidget(self._divider())
        layout.addWidget(QLabel("Diff Threshold"))
        self._threshold_label = QLabel("8")
        self._threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self._threshold_slider.setMinimum(1)
        self._threshold_slider.setMaximum(30)
        self._threshold_slider.setValue(8)
        self._threshold_slider.valueChanged.connect(
            lambda v: (
                self._threshold_label.setText(str(v)),
                self.diff_threshold_changed.emit(float(v)),
            )
        )
        row = QHBoxLayout()
        row.addWidget(self._threshold_slider)
        row.addWidget(self._threshold_label)
        layout.addLayout(row)

        # Action buttons
        layout.addWidget(self._divider())
        unload_btn = QPushButton("Unload Engines")
        unload_btn.clicked.connect(self.unload_engines_requested)
        layout.addWidget(unload_btn)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setStyleSheet("color: #ff6b6b;")
        reset_btn.clicked.connect(self.reset_requested)
        layout.addWidget(reset_btn)

        layout.addStretch()

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #333;")
        return line

    def _add_toggle_section(self, layout, title: str,
                           signal: pyqtSignal, default: bool):
        layout.addWidget(QLabel(title))
        row = QHBoxLayout()
        on_btn = QPushButton("On")
        off_btn = QPushButton("Off")
        on_btn.setProperty("class", "option-btn")
        off_btn.setProperty("class", "option-btn")
        on_btn.setCheckable(True)
        off_btn.setCheckable(True)
        on_btn.setChecked(default)
        off_btn.setChecked(not default)

        def _on_clicked():
            on_btn.setChecked(True)
            off_btn.setChecked(False)
            signal.emit(True)

        def _off_clicked():
            on_btn.setChecked(False)
            off_btn.setChecked(True)
            signal.emit(False)

        on_btn.clicked.connect(_on_clicked)
        off_btn.clicked.connect(_off_clicked)
        row.addWidget(on_btn)
        row.addWidget(off_btn)
        row.addStretch()
        layout.addLayout(row)
