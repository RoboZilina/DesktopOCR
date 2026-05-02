"""Header controls bar — mirrors web app's top nav bar."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt
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
        self._menu_btn = QPushButton("Menu ▾")
        self._menu_btn.setObjectName("MenuButton")
        self._menu_btn.setCheckable(True)
        self._menu_btn.setFixedHeight(34)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setToolTip("Open side menu (settings, Anki, guides)")
        self._menu_btn.toggled.connect(self._on_menu_toggled)
        self._menu_open = False
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
        for engine in engines:
            label = self._format_engine_label(engine)
            self._engine_combo.addItem(label, engine)
        self._engine_combo.setStyleSheet(_combo_style(DARK))
        self._engine_combo.currentIndexChanged.connect(self._emit_engine_change)
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
        idx = self._engine_combo.findData(engine_id)
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

    def _emit_engine_change(self, index: int):
        data = self._engine_combo.itemData(index)
        if data:
            self.engine_changed.emit(data)

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
        hover_bg = "rgba(255, 255, 255, 0.08)" if pal.is_dark else "rgba(0, 0, 0, 0.06)"
        pressed_bg = "rgba(255, 255, 255, 0.14)" if pal.is_dark else "rgba(0, 0, 0, 0.12)"
        checked_bg = "rgba(255, 255, 255, 0.16)" if pal.is_dark else "rgba(0, 0, 0, 0.16)"
        self._menu_btn.setStyleSheet(
            f"""
            QPushButton#MenuButton {{
                border: none;
                background: transparent;
                padding: 4px 10px;
                color: {pal.text};
                font-size: 13px;
                font-weight: 500;
                border-radius: 6px;
            }}
            QPushButton#MenuButton:hover {{
                background: {hover_bg};
            }}
            QPushButton#MenuButton:pressed {{
                background: {pressed_bg};
                font-weight: 600;
            }}
            QPushButton#MenuButton:checked {{
                background: {checked_bg};
                font-weight: 600;
            }}
            """
        )
        self._update_menu_label(self._menu_open)
        self._engine_lbl.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        self._voice_lbl.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        self.voice_selector.setStyleSheet(_combo_style(pal))

    def set_menu_icon(self, opened: bool):
        self._menu_open = opened
        block = self._menu_btn.blockSignals(True)
        self._menu_btn.setChecked(opened)
        self._menu_btn.blockSignals(block)
        self._update_menu_label(opened)

    def _style_button(self, btn: QPushButton):
        btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        btn.setMinimumHeight(28)
        btn.setMinimumWidth(32)

    def _update_menu_label(self, opened: bool) -> None:
        self._menu_btn.setText("Menu ▴" if opened else "Menu ▾")

    def _on_menu_toggled(self, checked: bool) -> None:
        self._menu_open = checked
        self._update_menu_label(checked)
        self.menu_requested.emit()

    def _format_engine_label(self, engine_id: str) -> str:
        engine_id = engine_id or ""
        if engine_id.startswith("paddle-"):
            try:
                line_count = int(engine_id.split("-", 1)[1])
            except (ValueError, IndexError):
                line_count = 1
            line_word = "line" if line_count == 1 else "lines"
            return f"Paddle — {line_count} {line_word}"
        if engine_id == "windows_ocr":
            return "Windows OCR"
        return engine_id.replace("_", " ").title()

