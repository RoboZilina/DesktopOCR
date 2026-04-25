"""
Transcription tray — sits below the preview, left column.
Three text areas: OCR output, full translation, selection translation.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import ThemePalette


TRAY_HEIGHTS = {
    "small":  80,
    "medium": 112,
    "large":  160,
}

FONT_SIZES = {
    "small":  18,
    "medium": 26,
    "large":  36,
}


class TranscriptionTray(QWidget):
    recapture_requested = pyqtSignal()
    tts_requested       = pyqtSignal(str)   # text to speak
    translate_requested = pyqtSignal(str)   # text to translate (full)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border-top: 1px solid transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # --- OCR output row ---
        ocr_header = QHBoxLayout()
        ocr_label = QLabel("OCR Output")
        ocr_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        ocr_header.addWidget(ocr_label)
        ocr_header.addStretch()

        self._recapture_btn = QPushButton("🔄 Re-capture")
        self._recapture_btn.setFixedHeight(28)
        self._recapture_btn.setStyleSheet(
            "background: #10b981; color: #000000; border: none; "
            "border-radius: 6px; padding: 4px 14px; font-weight: 700; font-size: 12px;"
        )
        self._recapture_btn.clicked.connect(lambda: self.recapture_requested.emit())
        ocr_header.addWidget(self._recapture_btn)
        layout.addLayout(ocr_header)

        self._ocr_text = QTextEdit()
        self._ocr_text.setReadOnly(False)  # user can select text
        self._ocr_text.setStyleSheet(self._text_style(large=True))
        self._ocr_text.setPlaceholderText("OCR output will appear here...")
        # Wire selection change → populate selection box
        self._ocr_text.selectionChanged.connect(self._on_selection_changed)
        self._ocr_scroll = QScrollArea()
        self._ocr_scroll.setWidgetResizable(True)
        self._ocr_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._ocr_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._ocr_scroll.setWidget(self._ocr_text)
        layout.addWidget(self._ocr_scroll)

        # --- Selection row ---
        sel_header = QHBoxLayout()
        sel_label = QLabel("Selection")
        sel_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        sel_header.addWidget(sel_label)
        sel_header.addStretch()


        self._speak_btn = QPushButton("\U0001F50A")
        self._speak_btn.setFlat(True)
        self._speak_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._speak_btn.clicked.connect(
            lambda: self.tts_requested.emit(
                self._sel_text.toPlainText() or self._ocr_text.toPlainText()
            )
        )
        sel_header.addWidget(self._speak_btn)
        self._translate_btn = QPushButton("🌐 Translate")
        self._translate_btn.setFixedHeight(28)
        self._translate_btn.setStyleSheet(
            "background: #10b981; color: #000000; border: none; "
            "border-radius: 6px; padding: 4px 14px; font-weight: 700; font-size: 12px;"
        )
        self._translate_btn.clicked.connect(
            lambda: self.translate_requested.emit(self._sel_text.toPlainText())
        )
        sel_header.addWidget(self._translate_btn)
        layout.addLayout(sel_header)

        self._sel_text = QTextEdit()
        self._sel_text.setReadOnly(True)
        self._sel_text.setStyleSheet(self._text_style())
        self._sel_text.setPlaceholderText(
            "Highlight text above to translate selection..."
        )
        self._sel_scroll = QScrollArea()
        self._sel_scroll.setWidgetResizable(True)
        self._sel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._sel_scroll.setWidget(self._sel_text)
        layout.addWidget(self._sel_scroll)

        # --- Full translation row ---
        trans_header = QHBoxLayout()
        trans_label = QLabel("Translation")
        trans_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        trans_header.addWidget(trans_label)
        trans_header.addStretch()
        layout.addLayout(trans_header)

        self._trans_text = QTextEdit()
        self._trans_text.setReadOnly(True)
        self._trans_text.setStyleSheet(self._text_style())
        self._trans_text.setPlaceholderText("Translation will appear here...")
        self._trans_scroll = QScrollArea()
        self._trans_scroll.setWidgetResizable(True)
        self._trans_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._trans_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._trans_scroll.setWidget(self._trans_text)
        layout.addWidget(self._trans_scroll)

        self.set_text_size("medium")
        self.set_tray_height("medium")

    def _text_style(self, large=False, size=None) -> str:
        if size is None:
            size = 26 if large else 18
        pal = getattr(self, '_pal', None)
        bg = pal.bg if pal else "#050506"
        text = pal.text if pal else "#ffffff"
        border = pal.border if pal else "#1f1f23"
        return f"""
            QTextEdit {{
                background: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                font-size: {size}px;
                padding: 6px;
            }}
        """

    def _on_selection_changed(self):
        """Auto-populate selection translation box when user highlights text."""
        cursor = self._ocr_text.textCursor()
        selected = cursor.selectedText().strip()
        if selected:
            self._sel_text.setPlaceholderText(f'Selected: "{selected}"')
            # Actual translation fired externally via signal in Stage 6b/6c
            # For now just show what's selected
            self._sel_text.setPlainText(selected)

    # --- Public API ---

    def set_text_size(self, size_id: str):
        if size_id not in FONT_SIZES:
            return
        self._current_font_size = size_id
        font_size = FONT_SIZES[size_id]
        self._ocr_text.setStyleSheet(self._text_style(large=True, size=font_size))
        self._trans_text.setStyleSheet(self._text_style(size=font_size))
        self._sel_text.setStyleSheet(self._text_style(size=font_size))

    def set_tray_height(self, size_id: str):
        if size_id not in TRAY_HEIGHTS:
            return
        self._current_height = size_id
        height = TRAY_HEIGHTS[size_id]
        self._ocr_scroll.setFixedHeight(height)
        self._trans_scroll.setFixedHeight(height)
        self._sel_scroll.setFixedHeight(height)

    def set_theme(self, pal: ThemePalette):
        self._pal = pal
        # Re-apply tray background
        self.setStyleSheet(f"background: {pal.panel}; border-top: 1px solid {pal.border};")
        # Re-apply label colors
        for lbl in (self.findChildren(QLabel)):
            lbl.setStyleSheet(f"color: {pal.text_dim}; font-size: 11px;")
        # Re-apply text areas
        if hasattr(self, '_current_font_size'):
            self.set_text_size(self._current_font_size)
        # Re-apply buttons
        self._recapture_btn.setStyleSheet(
            f"background: {pal.accent}; color: {pal.bg if pal.is_dark else '#ffffff'}; border: none; "
            "border-radius: 6px; padding: 4px 14px; font-weight: 700; font-size: 12px;"
        )
        self._translate_btn.setStyleSheet(
            f"background: {pal.accent}; color: {pal.bg if pal.is_dark else '#ffffff'}; border: none; "
            "border-radius: 6px; padding: 4px 14px; font-weight: 700; font-size: 12px;"
        )
        icon_bg = "#1a1a1f" if pal.is_dark else "#e2e8f0"
        self._speak_btn.setStyleSheet(
            f"background: {icon_bg}; color: {pal.accent}; border: 1px solid {pal.border}; "
            "border-radius: 6px; font-size: 14px;"
        )

    def set_ocr_text(self, text: str):
        self._ocr_text.setPlainText(text)

    def set_translation(self, text: str):
        self._trans_text.setPlainText(text)

    def set_selection_translation(self, text: str):
        self._sel_text.setPlainText(text)

    def get_ocr_text(self) -> str:
        return self._ocr_text.toPlainText()
