"""
History sidebar — right column, 340px fixed width.
Each OCR result is a card with hover-reveal action buttons.
Mirrors web app's .history-sidebar + .history-item pattern.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal


class HistoryCard(QWidget):
    tts_requested       = pyqtSignal(str)
    translate_requested = pyqtSignal(str)
    copy_requested      = pyqtSignal(str)

    def __init__(self, timestamp: str, engine: str,
                 conf: float, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self.setStyleSheet("""
            QWidget {
                background: #0d0d10;
                border: 1px solid #1f1f23;
                border-left: 3px solid #10b981;
                border-radius: 6px;
            }
            QWidget:hover {
                background: rgba(255,255,255,0.03);
                border-color: #10b981;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Metadata row
        meta = QLabel(f"{timestamp} · {engine} · {conf:.2f}")
        meta.setStyleSheet("color: #52525b; font-size: 10px; border: none;")
        layout.addWidget(meta)

        # Text
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text_label.setStyleSheet(
            "color: #a1a1aa; font-size: 13px; border: none;"
        )
        layout.addWidget(text_label)

        # Action buttons row (always visible, subtle)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        for icon, tip, signal in [
            ("🔊", "Speak",     self.tts_requested),
            ("🌐", "Translate", self.translate_requested),
            ("📋", "Copy",      self.copy_requested),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.setStyleSheet("""
                QPushButton {
                    background: none;
                    border: none;
                    font-size: 14px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.1);
                }
            """)
            btn.clicked.connect(lambda _, s=signal: s.emit(self._text))
            btn_row.addWidget(btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)


class HistorySidebar(QWidget):
    tts_requested       = pyqtSignal(str)
    translate_requested = pyqtSignal(str)

    MAX_ENTRIES = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)
        self.setStyleSheet("background: #08080a;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(
            "background: #08080a; border-bottom: 1px solid #1f1f23;"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("HISTORY")
        title.setStyleSheet(
            "color: #a1a1aa; font-size: 12px; "
            "font-weight: bold; letter-spacing: 1px;"
        )
        h_layout.addWidget(title)
        h_layout.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(28)
        clear_btn.setStyleSheet(
            "color: #a1a1aa; background: none; "
            "border: 1px solid #1f1f23; border-radius: 4px;"
        )
        clear_btn.clicked.connect(self._clear)
        h_layout.addWidget(clear_btn)
        outer.addWidget(header)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: #08080a; }"
        )

        self._container = QWidget()
        self._container.setStyleSheet("background: #08080a;")
        self._cards_layout = QVBoxLayout(self._container)
        self._cards_layout.setContentsMargins(12, 12, 12, 12)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        self._last_text: str | None = None
        self._entry_count = 0

    def add_entry(self, timestamp: str, engine: str,
                  conf: float, text: str):
        if text == self._last_text:
            return
        self._last_text = text

        card = HistoryCard(timestamp, engine, conf, text)
        card.tts_requested.connect(self.tts_requested)
        card.translate_requested.connect(self.translate_requested)
        card.copy_requested.connect(self._copy_text)

        # Insert at top (index 0, before the stretch)
        self._cards_layout.insertWidget(0, card)
        self._entry_count += 1

        # Trim oldest
        if self._entry_count > self.MAX_ENTRIES:
            item = self._cards_layout.takeAt(self._cards_layout.count() - 2)
            if item and item.widget():
                item.widget().deleteLater()
            self._entry_count -= 1

    def _copy_text(self, text: str):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _clear(self):
        while self._cards_layout.count() > 1:  # keep the stretch
            item = self._cards_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._last_text = None
        self._entry_count = 0
