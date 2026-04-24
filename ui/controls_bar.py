"""Header controls bar — mirrors web app's top nav bar."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton
from PyQt6.QtCore import pyqtSignal
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

    def __init__(self, engines: list[str], parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(
            "background: transparent; border-bottom: 1px solid transparent;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        # Brand / Menu
        self._menu_btn = QPushButton("☰")
        self._menu_btn.setFixedSize(32, 32)
        self._menu_btn.setStyleSheet(
            "background: none; border: none; color: #a1a1aa; font-size: 14px;"
        )
        self._menu_btn.clicked.connect(self.menu_requested)
        layout.addWidget(self._menu_btn)

        brand = QLabel("Personal OCR")
        brand.setObjectName("PersonalOCR")
        brand.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: 800; letter-spacing: 0.5px;"
        )
        layout.addWidget(brand)

        layout.addSpacing(24)

        # Engine selector
        self._engine_lbl = QLabel("Engine")
        self._engine_lbl.setStyleSheet("color: #52525b; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._engine_lbl)
        self._engine_combo = QComboBox()
        self._engine_combo.addItems(engines)
        self._engine_combo.setStyleSheet(_combo_style(DARK))
        self._engine_combo.currentTextChanged.connect(self.engine_changed.emit)
        layout.addWidget(self._engine_combo)

        layout.addSpacing(12)

        # Mode selector
        self._mode_lbl = QLabel("Mode")
        self._mode_lbl.setStyleSheet("color: #52525b; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._mode_lbl)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["baseline-reset"])
        self._mode_combo.setEnabled(False)
        self._mode_combo.setStyleSheet(_combo_style(DARK))
        layout.addWidget(self._mode_combo)

        layout.addStretch()

    def set_engine(self, engine_id: str):
        """Set combo without firing signal."""
        self._engine_combo.blockSignals(True)
        idx = self._engine_combo.findText(engine_id)
        if idx >= 0:
            self._engine_combo.setCurrentIndex(idx)
        self._engine_combo.blockSignals(False)

    def set_theme(self, pal: ThemePalette):
        self.setStyleSheet(
            f"background: {pal.panel}; border-bottom: 1px solid {pal.border};"
        )
        self._engine_combo.setStyleSheet(_combo_style(pal))
        self._mode_combo.setStyleSheet(_combo_style(pal))
        brand = self.findChild(QLabel, "PersonalOCR")
        if brand:
            brand.setStyleSheet(
                f"color: {pal.text}; font-size: 14px; font-weight: 800; letter-spacing: 0.5px;"
            )
        self._menu_btn.setStyleSheet(
            f"background: none; border: none; color: {pal.text}; font-size: 14px;"
        )
        self._engine_lbl.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: bold;"
        )
        self._mode_lbl.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: bold;"
        )
