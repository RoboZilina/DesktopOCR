"""Slide-in side menu panel — mirrors web app's #side-menu."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPalette, QColor
from ui.theme import ThemePalette, DARK, LIGHT


class SideMenu(QWidget):
    """Right-edge overlay panel with toggle sections and action buttons."""

    auto_capture_changed     = pyqtSignal(bool)
    auto_copy_changed        = pyqtSignal(bool)
    history_visible_changed  = pyqtSignal(bool)
    preview_visible_changed  = pyqtSignal(bool)
    vn_cleaner_changed       = pyqtSignal(bool)
    diff_threshold_changed   = pyqtSignal(float)
    text_size_changed        = pyqtSignal(str)
    tray_height_changed      = pyqtSignal(str)
    theme_changed            = pyqtSignal(str)  # "auto" | "dark" | "light"
    reset_requested          = pyqtSignal()
    unload_engines_requested = pyqtSignal()
    hide_requested           = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)
        self.setObjectName("SideMenu")
        self.setAutoFillBackground(True)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        self._header = QLabel("SIDE MENU")
        layout.addWidget(self._header)
        layout.addWidget(self._divider())

        # Theme toggle
        layout.addWidget(QLabel("Theme"))
        theme_row = QHBoxLayout()
        self._theme_btns = {}
        for label, tid in [("Auto", "auto"), ("Dark", "dark"), ("Light", "light")]:
            btn = QPushButton(label)
            btn.setProperty("class", "option-btn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, t=tid: self._on_theme_clicked(t))
            theme_row.addWidget(btn)
            self._theme_btns[tid] = btn
        self._theme_btns["auto"].setChecked(True)
        theme_row.addStretch()
        layout.addLayout(theme_row)
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

        # Text size preset (font)
        layout.addWidget(self._divider())
        layout.addWidget(QLabel("Text Size"))
        size_row = QHBoxLayout()
        self._size_btns = {}
        for label, sid in [("S", "small"), ("M", "medium"), ("L", "large")]:
            btn = QPushButton(label)
            btn.setProperty("class", "option-btn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, s=sid: self._on_text_size_clicked(s))
            size_row.addWidget(btn)
            self._size_btns[sid] = btn
        self._size_btns["medium"].setChecked(True)
        size_row.addStretch()
        layout.addLayout(size_row)

        # Text area size preset (tray height)
        layout.addWidget(QLabel("Text Area Size"))
        tray_row = QHBoxLayout()
        self._tray_size_btns = {}
        for label, sid in [("S", "small"), ("M", "medium"), ("L", "large")]:
            btn = QPushButton(label)
            btn.setProperty("class", "option-btn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, s=sid: self._on_tray_height_clicked(s))
            tray_row.addWidget(btn)
            self._tray_size_btns[sid] = btn
        self._tray_size_btns["medium"].setChecked(True)
        tray_row.addStretch()
        layout.addLayout(tray_row)

        # Action buttons
        layout.addWidget(self._divider())
        unload_btn = QPushButton("Unload Engines")
        unload_btn.clicked.connect(self.unload_engines_requested)
        layout.addWidget(unload_btn)

        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(self._reset_btn)

        layout.addStretch()

        # Auto-close menu after any button interaction
        for btn in self.findChildren(QPushButton):
            btn.clicked.connect(self.hide_requested)

        # Apply initial stylesheet
        self._apply_base_style()

    def _apply_base_style(self):
        pal = getattr(self, '_pal', None)
        bg = pal.panel if pal else "#0d0d10"
        border = pal.border if pal else "#1f1f23"
        text_dim = pal.text_dim if pal else "#8a8a93"
        accent = pal.accent if pal else "#10b981"
        btn_bg = "#1a1a1f" if (not pal or pal.is_dark) else "#f1f5f9"
        btn_border = "#2a2a2f" if (not pal or pal.is_dark) else "#cbd5e1"
        btn_hover = "#3a3a3f" if (not pal or pal.is_dark) else "#94a3b8"
        groove = "#2a2a2f" if (not pal or pal.is_dark) else "#e2e8f0"
        checked_fg = "#000000" if (not pal or pal.is_dark) else "#ffffff"
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(bg))
        self.setPalette(palette)
        self.setStyleSheet(
            f"background-color: {bg}; border-right: 1px solid {border};"
            + f"""
            QLabel {{ color: {text_dim}; font-size: 14px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }}
            QPushButton[class="option-btn"] {{
                background: {btn_bg};
                color: {text_dim};
                border: 1px solid {btn_border};
                border-radius: 8px;
                padding: 7px 16px;
                font-size: 15px;
                font-weight: 600;
            }}
            QPushButton[class="option-btn"]:checked {{
                background: {accent};
                color: {checked_fg};
                border-color: {accent};
            }}
            QPushButton[class="option-btn"]:hover {{
                border-color: {btn_hover};
            }}
            QSlider::groove:horizontal {{
                background: {groove};
                height: 5px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {accent};
                width: 18px;
                height: 18px;
                border-radius: 9px;
                margin: -7px 0;
            }}
            """
        )

    def _on_text_size_clicked(self, size_id: str):
        for sid, btn in self._size_btns.items():
            btn.setChecked(sid == size_id)
        self.text_size_changed.emit(size_id)

    def _on_tray_height_clicked(self, size_id: str):
        for sid, btn in self._tray_size_btns.items():
            btn.setChecked(sid == size_id)
        self.tray_height_changed.emit(size_id)

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        pal = getattr(self, '_pal', None)
        border = pal.border if pal else "#1f1f23"
        line.setStyleSheet(f"background: {border}; max-height: 1px;")
        return line

    def _on_theme_clicked(self, theme_id: str):
        for tid, btn in self._theme_btns.items():
            btn.setChecked(tid == theme_id)
        self.theme_changed.emit(theme_id)

    def set_theme(self, pal: ThemePalette):
        self._pal = pal
        self._apply_base_style()
        # Update header label
        self._header.setStyleSheet(
            f"color: {pal.text}; font-size: 18px; font-weight: 800; letter-spacing: 1px;"
        )
        # Update reset button color
        self._reset_btn.setStyleSheet(f"color: {pal.panic};")

    def _on_reset(self):
        # Reset toggles to their defaults
        self._size_btns["medium"].setChecked(True)
        for sid, btn in self._size_btns.items():
            if sid != "medium":
                btn.setChecked(False)
        self.text_size_changed.emit("medium")
        self._tray_size_btns["medium"].setChecked(True)
        for sid, btn in self._tray_size_btns.items():
            if sid != "medium":
                btn.setChecked(False)
        self.tray_height_changed.emit("medium")
        self._theme_btns["auto"].setChecked(True)
        for tid, btn in self._theme_btns.items():
            if tid != "auto":
                btn.setChecked(False)
        self.theme_changed.emit("auto")
        self.reset_requested.emit()

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
