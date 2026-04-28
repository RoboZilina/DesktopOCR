"""
Transcription tray — sits below the preview, left column.
Three text areas: OCR output, full translation, selection translation.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QFrame, QScrollArea, QSizePolicy,
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


def _blend_hex(base: str, target: str, ratio: float) -> str:
    """Linearly blend two hex colors."""
    def _to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        return tuple(int(value[i:i+2], 16) for i in range(0, 6, 2))

    br, bg, bb = _to_rgb(base or "#000000")
    tr, tg, tb = _to_rgb(target or "#000000")
    rr = round(br + (tr - br) * ratio)
    rg = round(bg + (tg - bg) * ratio)
    rb = round(bb + (tb - bb) * ratio)
    return f"#{rr:02x}{rg:02x}{rb:02x}"


class TranscriptionTray(QWidget):
    recapture_requested = pyqtSignal()
    tts_requested       = pyqtSignal(str)   # text to speak
    translate_requested = pyqtSignal(str)   # text to translate (full)
    selection_changed   = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border-top: 1px solid transparent;")
        self._primary_buttons: list[QPushButton] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # --- OCR output row ---
        ocr_header = QHBoxLayout()
        ocr_header.setContentsMargins(0, 0, 0, 0)
        ocr_header.setSpacing(8)
        ocr_header.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ocr_label = self._make_header_label("OCR Output")
        ocr_header.addWidget(ocr_label)
        ocr_header.addStretch()

        self._recapture_btn = QPushButton("Re-capture")
        self._recapture_btn.setFixedHeight(28)
        self._recapture_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._recapture_btn.clicked.connect(lambda: self.recapture_requested.emit())
        self._primary_buttons.append(self._recapture_btn)
        ocr_header.addWidget(self._recapture_btn)
        layout.addLayout(ocr_header)

        self._ocr_text = QTextEdit()
        self._ocr_text.setReadOnly(False)  # user can select text
        self._ocr_text.setStyleSheet(self._text_style(large=True))
        self._ocr_text.setPlaceholderText(
            "Captured OCR text appears here. Keep the selection tight around actual text lines."
        )
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
        sel_header.setContentsMargins(0, 0, 0, 0)
        sel_header.setSpacing(8)
        sel_header.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        sel_label = self._make_header_label("Selection")
        sel_header.addWidget(sel_label)
        sel_header.addStretch()


        self._speak_btn = QPushButton("Speak")
        self._speak_btn.setFixedHeight(28)
        self._speak_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._speak_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self._speak_btn.clicked.connect(
            lambda: self.tts_requested.emit(
                self._sel_text.toPlainText() or self._ocr_text.toPlainText()
            )
        )
        self._primary_buttons.append(self._speak_btn)
        sel_header.addWidget(self._speak_btn)
        self._translate_btn = QPushButton("Translate")
        self._translate_btn.setFixedHeight(28)
        self._translate_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._translate_btn.clicked.connect(
            lambda: self.translate_requested.emit(self._sel_text.toPlainText())
        )
        self._primary_buttons.append(self._translate_btn)
        sel_header.addWidget(self._translate_btn)
        layout.addLayout(sel_header)

        self._sel_text = QTextEdit()
        self._sel_text.setReadOnly(True)
        self._sel_text.setStyleSheet(self._text_style())
        self._sel_text.setPlaceholderText(
            "Highlight text in the OCR pane and it will copy here automatically."
        )
        self._sel_scroll = QScrollArea()
        self._sel_scroll.setWidgetResizable(True)
        self._sel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._sel_scroll.setWidget(self._sel_text)
        layout.addWidget(self._sel_scroll)

        # --- Full translation row ---
        trans_header = QHBoxLayout()
        trans_label = self._make_header_label("Translation")
        trans_header.addWidget(trans_label)
        trans_header.addStretch()
        layout.addLayout(trans_header)

        self._trans_text = QTextEdit()
        self._trans_text.setReadOnly(True)
        self._trans_text.setStyleSheet(self._text_style())
        self._trans_text.setPlaceholderText("Click Translate to see the selection rendered in English.")
        self._trans_scroll = QScrollArea()
        self._trans_scroll.setWidgetResizable(True)
        self._trans_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._trans_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._trans_scroll.setWidget(self._trans_text)
        layout.addWidget(self._trans_scroll)

        # Apply base styling for primary buttons
        self._apply_primary_button_styles()

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
            self.selection_changed.emit(selected)
        else:
            self.selection_changed.emit("")

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
            lbl.setStyleSheet(f"color: {pal.text_dim}; font-size: 11px; background: transparent;")
        # Re-apply text areas
        if hasattr(self, '_current_font_size'):
            self.set_text_size(self._current_font_size)
        # Re-apply buttons
        self._apply_primary_button_styles()

    def set_ocr_text(self, text: str):
        self._ocr_text.setPlainText(text)

    def set_translation(self, text: str):
        self._trans_text.setPlainText(text)

    def set_selection_translation(self, text: str):
        self._sel_text.setPlainText(text)

    def set_translating(self, busy: bool) -> None:
        """Toggle translate button loading state."""
        if busy:
            self._translate_btn.setEnabled(False)
            self._translate_btn.setText("Translating...")
        else:
            self._translate_btn.setEnabled(True)
            self._translate_btn.setText("Translate")

    def set_translation_error(self, message: str) -> None:
        """Display error message in the translation area with panic color."""
        pal = getattr(self, '_pal', None)
        error_color = pal.panic if pal else "#ef4444"
        self._trans_text.setPlainText(message)
        # Temporarily apply error text color
        current_style = self._trans_text.styleSheet()
        size = FONT_SIZES.get(
            getattr(self, '_current_font_size', 'medium'), 18
        )
        bg = pal.bg if pal else "#050506"
        border = pal.border if pal else "#1f1f23"
        self._trans_text.setStyleSheet(f"""
            QTextEdit {{
                background: {bg};
                color: {error_color};
                border: 1px solid {error_color};
                border-radius: 6px;
                font-size: {size}px;
                padding: 6px;
            }}
        """)

    def _make_header_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_header")
        lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lbl.setStyleSheet("background: transparent; border: none;")
        return lbl

    def _apply_primary_button_styles(self) -> None:
        pal = getattr(self, '_pal', None)
        accent = pal.accent if pal else "#10b981"
        text_color = pal.bg if pal and pal.is_dark else "#ffffff"
        hover = _blend_hex(accent, "#ffffff", 0.15)
        pressed = _blend_hex(accent, "#000000", 0.18)
        style = (
            f"QPushButton {{"
            f" background: {accent};"
            f" color: {text_color};"
            " border: none; border-radius: 6px; padding: 4px 14px;"
            " font-weight: 700; font-size: 12px;"
            " margin-top: 0px; margin-bottom: 0px;"
            "}"
            f"QPushButton:hover {{ background: {hover}; margin-top: -1px; margin-bottom: 1px; }}"
            f"QPushButton:pressed {{ background: {pressed}; margin-top: 0px; margin-bottom: 0px; }}"
            "QPushButton:disabled { opacity: 0.6; margin-top: 0px; margin-bottom: 0px; }"
        )
        for btn in getattr(self, '_primary_buttons', []):
            btn.setStyleSheet(style)

    def get_ocr_text(self) -> str:
        return self._ocr_text.toPlainText()

    def get_selection_text(self) -> str:
        return self._sel_text.toPlainText()
