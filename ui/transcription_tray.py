"""
Transcription tray — sits below the preview, left column.
Three text areas: OCR output, full translation, selection translation.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal


class TranscriptionTray(QWidget):
    recapture_requested = pyqtSignal()
    tts_requested       = pyqtSignal(str)   # text to speak
    translate_requested = pyqtSignal(str)   # text to translate (full)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(280)
        self.setStyleSheet("background: #0d0d10; border-top: 1px solid #1f1f23;")

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
        self._recapture_btn.clicked.connect(self.recapture_requested)
        ocr_header.addWidget(self._recapture_btn)

        self._speak_btn = QPushButton("🔊")
        self._speak_btn.setFixedSize(28, 28)
        self._speak_btn.setToolTip("Speak OCR text")
        self._speak_btn.clicked.connect(
            lambda: self.tts_requested.emit(self._ocr_text.toPlainText())
        )
        ocr_header.addWidget(self._speak_btn)
        layout.addLayout(ocr_header)

        self._ocr_text = QTextEdit()
        self._ocr_text.setReadOnly(False)  # user can select text
        self._ocr_text.setFixedHeight(72)
        self._ocr_text.setStyleSheet(self._text_style(large=True))
        self._ocr_text.setPlaceholderText("OCR output will appear here...")
        # Wire selection change → populate selection translation box
        self._ocr_text.selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._ocr_text)

        # --- Full translation row ---
        trans_header = QHBoxLayout()
        trans_label = QLabel("Translation")
        trans_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        trans_header.addWidget(trans_label)
        trans_header.addStretch()

        self._translate_btn = QPushButton("🌐 Translate")
        self._translate_btn.setFixedHeight(28)
        self._translate_btn.clicked.connect(
            lambda: self.translate_requested.emit(self._ocr_text.toPlainText())
        )
        trans_header.addWidget(self._translate_btn)

        self._speak_trans_btn = QPushButton("🔊")
        self._speak_trans_btn.setFixedSize(28, 28)
        self._speak_trans_btn.setToolTip("Speak translation")
        self._speak_trans_btn.clicked.connect(
            lambda: self.tts_requested.emit(self._trans_text.toPlainText())
        )
        trans_header.addWidget(self._speak_trans_btn)
        layout.addLayout(trans_header)

        self._trans_text = QTextEdit()
        self._trans_text.setReadOnly(True)
        self._trans_text.setFixedHeight(56)
        self._trans_text.setStyleSheet(self._text_style())
        self._trans_text.setPlaceholderText("Translation will appear here...")
        layout.addWidget(self._trans_text)

        # --- Selection translation row ---
        sel_label = QLabel("Selection Translation")
        sel_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        layout.addWidget(sel_label)

        self._sel_text = QTextEdit()
        self._sel_text.setReadOnly(True)
        self._sel_text.setFixedHeight(48)
        self._sel_text.setStyleSheet(self._text_style())
        self._sel_text.setPlaceholderText(
            "Highlight text above to translate selection..."
        )
        layout.addWidget(self._sel_text)

    def _text_style(self, large=False) -> str:
        size = "16px" if large else "13px"
        return f"""
            QTextEdit {{
                background: #050506;
                color: #ffffff;
                border: 1px solid #1f1f23;
                border-radius: 6px;
                font-size: {size};
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

    def set_ocr_text(self, text: str):
        self._ocr_text.setPlainText(text)

    def set_translation(self, text: str):
        self._trans_text.setPlainText(text)

    def set_selection_translation(self, text: str):
        self._sel_text.setPlainText(text)

    def get_ocr_text(self) -> str:
        return self._ocr_text.toPlainText()
