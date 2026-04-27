"""Header controls bar — mirrors web app's top nav bar."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from ui.theme import ThemePalette, DARK


def _combo_style(pal: ThemePalette) -> str:
    return f"""
    QComboBox {{
        background: {pal.panel};
        color: {pal.text_dim};
        border: 1px solid {pal.border};
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 13px;
    }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {pal.panel};
        color: {pal.text_dim};
        border: 1px solid {pal.border};
        selection-background-color: {pal.accent};
    }}
"""


class ControlsBar(QWidget):
    engine_changed = pyqtSignal(str)
    menu_requested = pyqtSignal()
    voice_changed = pyqtSignal(str)
    select_window_requested = pyqtSignal()
    stop_stream_requested = pyqtSignal()

    def __init__(self, engines: list[str], parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(
            "background: transparent; border-bottom: 1px solid transparent;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Brand / Menu
        self._menu_btn = QPushButton("☰")
        self._menu_btn.setObjectName("hamburger_button")
        self._style_button(self._menu_btn)
        self._menu_btn.clicked.connect(self.menu_requested)
        layout.addWidget(self._menu_btn)

        brand = QLabel("Personal OCR")
        brand.setObjectName("PersonalOCR")
        brand.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        brand.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: 800; letter-spacing: 0.5px; background: transparent; border: none;"
        )
        layout.addWidget(brand)

        layout.addSpacing(6)

        # Engine selector
        self._engine_lbl = QLabel("Engine")
        self._engine_lbl.setObjectName("section_header")
        self._engine_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._engine_lbl.setStyleSheet("color: #52525b; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(self._engine_lbl)
        self._engine_combo = QComboBox()
        self._engine_combo.addItems(engines)
        self._engine_combo.setStyleSheet(_combo_style(DARK))
        self._engine_combo.currentTextChanged.connect(self.engine_changed.emit)
        layout.addWidget(self._engine_combo)

        layout.addSpacing(6)

        # Voice selector
        self._voice_lbl = QLabel("Voice")
        self._voice_lbl.setObjectName("section_header")
        self._voice_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._voice_lbl.setStyleSheet("color: #52525b; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(self._voice_lbl)
        self.voice_selector = QComboBox()
        self.voice_selector.setObjectName("VoiceSelector")
        self.voice_selector.setMinimumWidth(180)
        self.voice_selector.setMaximumWidth(260)
        self.voice_selector.setStyleSheet(_combo_style(DARK))
        self.voice_selector.currentTextChanged.connect(self._emit_voice_change)
        layout.addWidget(self.voice_selector)

        layout.addSpacing(6)

        layout.addStretch()

        # Stream toggle button (green = select window, red = stop stream)
        self._stream_btn = QPushButton("Select Source Window")
        self._stream_btn.setObjectName("StreamButton")
        self._style_button(self._stream_btn)
        self._stream_btn.setMinimumWidth(210)
        self._stream_btn.clicked.connect(self._on_stream_btn_clicked)
        self._streaming = False
        self._update_stream_btn_style()
        layout.addWidget(self._stream_btn)

    def _update_stream_btn_style(self):
        if self._streaming:
            self._stream_btn.setText("Stop Stream")
            self._stream_btn.setStyleSheet(
                "background: #b91c1c; color: #fff; border: none; border-radius: 6px; font-weight: bold;"
            )
        else:
            self._stream_btn.setText("Select Source Window")
            self._stream_btn.setStyleSheet(
                "background: #059669; color: #fff; border: none; border-radius: 6px; font-weight: bold;"
            )

    def _on_stream_btn_clicked(self):
        if self._streaming:
            self.stop_stream_requested.emit()
            self._streaming = False
        else:
            self.select_window_requested.emit()
            self._streaming = True
        self._update_stream_btn_style()

    def set_streaming(self, streaming: bool):
        self._streaming = streaming
        self._update_stream_btn_style()

    def set_engine(self, engine_id: str):
        """Set combo without firing signal."""
        self._engine_combo.blockSignals(True)
        idx = self._engine_combo.findText(engine_id)
        if idx >= 0:
            self._engine_combo.setCurrentIndex(idx)
        self._engine_combo.blockSignals(False)


    def load_voices(self, voices):
        """
        Populate the voice selector with a list of (label, id) tuples.
        Example: [("System Voice — Default (ID 0)", 0)]
        """
        self.voice_selector.clear()
        self._voice_id_map = {}
        for label, vid in voices:
            self.voice_selector.addItem(label)
            self._voice_id_map[label] = vid

    def _emit_voice_change(self, text):
        if hasattr(self, "_voice_id_map") and text in self._voice_id_map:
            self.voice_changed.emit(self._voice_id_map[text])

    def set_theme(self, pal: ThemePalette):
        self.setStyleSheet(
            f"background: {pal.panel}; border-bottom: 1px solid {pal.border};"
        )
        self._engine_combo.setStyleSheet(_combo_style(pal))
        self.voice_selector.setStyleSheet(_combo_style(pal))
        brand = self.findChild(QLabel, "PersonalOCR")
        if brand:
            brand.setStyleSheet(
                f"color: {pal.text}; font-size: 14px; font-weight: 800; letter-spacing: 0.5px; background: transparent; border: none;"
            )
        hover_bg = "rgba(255, 255, 255, 0.12)" if pal.is_dark else "rgba(0, 0, 0, 0.08)"
        pressed_bg = "rgba(255, 255, 255, 0.2)" if pal.is_dark else "rgba(0, 0, 0, 0.14)"
        self._menu_btn.setStyleSheet(
            (
                f"QPushButton#hamburger_button {{"
                f" background: transparent;"
                f" border: none;"
                f" color: {pal.text};"
                f" font-size: 14px;"
                f" border-radius: 6px;"
                f" padding: 4px;"
                f" text-align: center;"
                f"}}"
                f"QPushButton#hamburger_button:hover {{"
                f" background-color: {hover_bg};"
                f"}}"
                f"QPushButton#hamburger_button:pressed {{"
                f" background-color: {pressed_bg};"
                f"}}"
            )
        )
        self._engine_lbl.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        self._voice_lbl.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        self.voice_selector.setStyleSheet(_combo_style(pal))

    def set_menu_icon(self, opened: bool):
        self._menu_btn.setText("✕" if opened else "☰")

    def _style_button(self, btn: QPushButton):
        btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        btn.setMinimumHeight(28)
        btn.setMinimumWidth(32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("role", "button")
        btn.setIconSize(QSize(16, 16))
        btn.setStyleSheet("text-align: center; padding: 4px 8px;")
