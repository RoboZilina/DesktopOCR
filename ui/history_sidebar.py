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
from ui.theme import ThemePalette, DARK


class HistoryCard(QWidget):
    tts_requested       = pyqtSignal(str)
    translate_requested = pyqtSignal(str)
    copy_requested      = pyqtSignal(str)

    def __init__(self, timestamp: str, engine: str,
                 conf: float, text: str, pal: ThemePalette, parent=None):
        super().__init__(parent)
        self._text = text
        self._pal = pal
        self._timestamp = timestamp
        self._engine = engine
        self._conf = conf

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Metadata row
        self._meta = QLabel(f"{timestamp} · {engine} · {conf:.2f}")
        layout.addWidget(self._meta)

        # Text
        self._text_label = QLabel(text)
        self._text_label.setWordWrap(True)
        self._text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._text_label)

        # Action buttons row (always visible, subtle)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        for icon, tip, signal in [
            ("🔊", "Speak",     self.tts_requested),
            ("🌐", "Translate", self.translate_requested),
            ("📋", "Copy",      self.copy_requested),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(32, 32)
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_row.addWidget(btn)
            btn.clicked.connect(lambda _, s=signal: s.emit(self._text))

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._apply_pal()

    def _apply_pal(self):
        p = self._pal
        hover_bg = "rgba(255,255,255,0.03)" if p.is_dark else "rgba(0,0,0,0.03)"
        btn_hover = "rgba(255,255,255,0.1)" if p.is_dark else "rgba(0,0,0,0.1)"
        btn_bg = "#1a1a1f" if p.is_dark else "#f1f5f9"
        btn_border = "#2a2a2f" if p.is_dark else "#cbd5e1"
        self.setStyleSheet(f"""
            QWidget {{
                background: {p.panel};
                border: 1px solid {p.border};
                border-left: 3px solid {p.accent};
                border-radius: 6px;
            }}
            QWidget:hover {{
                background: {hover_bg};
                border-color: {p.accent};
            }}
            QPushButton {{
                background: {btn_bg};
                border: 1px solid {btn_border};
                font-size: 14px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {btn_hover};
                border-color: {p.accent};
            }}
        """)
        self._meta.setStyleSheet(f"color: {p.text_secondary}; font-size: 10px; border: none;")
        self._text_label.setStyleSheet(f"color: {p.text_dim}; font-size: 13px; border: none;")

    def set_palette(self, pal: ThemePalette):
        self._pal = pal
        self._apply_pal()


class HistorySidebar(QWidget):
    tts_requested       = pyqtSignal(str)
    translate_requested = pyqtSignal(str)

    MAX_ENTRIES = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)
        self._pal = None  # set via set_theme before use

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        self._header = QWidget()
        self._header.setFixedHeight(48)
        self._header.setObjectName("section_header")
        self._header.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._header.setStyleSheet("background: transparent; border: none;")
        h_layout = QHBoxLayout(self._header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("HISTORY")
        title.setObjectName("section_header")
        title.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        title.setStyleSheet("background: transparent; border: none;")
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
        outer.addWidget(self._header)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(self._container)
        self._cards_layout.setContentsMargins(12, 12, 12, 12)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        self._last_entry_key: tuple[str, str] | None = None
        self._entry_count = 0

    def set_theme(self, pal: ThemePalette):
        self._pal = pal
        # Update own styles
        self.setStyleSheet(f"background: {pal.bg};")
        self._header.setStyleSheet("background: transparent; border: none;")
        self._container.setStyleSheet(f"background: {pal.bg};")
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {pal.bg}; }}"
        )
        # Update header and clear button styles via finding widgets
        for w in self.findChildren(QWidget):
            if isinstance(w, QPushButton) and w.text() == "Clear":
                w.setStyleSheet(
                    f"color: {pal.text_dim}; background: none; "
                    f"border: 1px solid {pal.border}; border-radius: 4px;"
                )
        # Update title label
        for lbl in self.findChildren(QLabel):
            if lbl.text() == "HISTORY":
                lbl.setStyleSheet(
                    f"color: {pal.text_dim}; font-size: 12px; font-weight: bold; letter-spacing: 1px; background: transparent; border: none;"
                )
        # Update all existing cards
        for i in range(self._cards_layout.count() - 1):  # skip stretch
            item = self._cards_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), HistoryCard):
                item.widget().set_palette(pal)

    def add_entry(self, timestamp: str, engine: str,
                  conf: float, text: str):
        key = self._build_dedupe_key(text, engine, timestamp)
        if key == self._last_entry_key:
            return
        self._last_entry_key = key

        card = HistoryCard(timestamp, engine, conf, text, self._pal or DARK)
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
        self._last_entry_key = None
        self._entry_count = 0

    def _build_dedupe_key(self, text: str, engine: str | None, timestamp: str) -> tuple[str, str]:
        if engine:
            return (text, engine)
        bucket = timestamp.rsplit(":", 1)[0] if ":" in timestamp else timestamp
        return (text, bucket)
