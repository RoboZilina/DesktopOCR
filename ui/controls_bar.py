"""Header controls bar for engine, mode, menu and recapture."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton
from PyQt6.QtCore import pyqtSignal


class ControlsBar(QWidget):
    engine_changed = pyqtSignal(str)
    menu_requested = pyqtSignal()
    recapture_clicked = pyqtSignal()

    def __init__(self, engines: list[str], parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Menu button
        menu_btn = QPushButton("☰")
        menu_btn.setFixedWidth(36)
        menu_btn.clicked.connect(self.menu_requested)
        layout.addWidget(menu_btn)

        layout.addSpacing(8)

        # Engine selector
        layout.addWidget(QLabel("Engine:"))
        self._engine_combo = QComboBox()
        self._engine_combo.addItems(engines)
        self._engine_combo.currentTextChanged.connect(self.engine_changed.emit)
        layout.addWidget(self._engine_combo)

        layout.addSpacing(16)

        # Mode selector (placeholder — disabled until pipeline mode system)
        layout.addWidget(QLabel("Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["baseline-reset"])
        self._mode_combo.setEnabled(False)
        layout.addWidget(self._mode_combo)

        layout.addStretch()

        # Re-capture button
        recapture_btn = QPushButton("🔄 Re-capture")
        recapture_btn.clicked.connect(self.recapture_clicked)
        layout.addWidget(recapture_btn)

    def set_engine(self, engine_id: str):
        """Set combo without firing signal."""
        self._engine_combo.blockSignals(True)
        idx = self._engine_combo.findText(engine_id)
        if idx >= 0:
            self._engine_combo.setCurrentIndex(idx)
        self._engine_combo.blockSignals(False)
