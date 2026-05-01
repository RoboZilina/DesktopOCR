"""
Transcription tray — sits below the preview, left column.
Three text areas: OCR output, full translation, selection translation.
"""

import logging
import os
import re
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QApplication,
    QMessageBox,
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QFrame, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QTextCharFormat, QTextCursor

from core.frequency import annotator as freq_annotator
from core.frequency import kanji_freq
from ui.theme import ThemePalette

logger = logging.getLogger(__name__)


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


@dataclass
class _RenderToken:
    surface: str
    lemma: str | None
    start: int
    end: int
    freq_rank: int | None = None


_JP_TOKEN_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]+")

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
    anki_requested      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border-top: 1px solid transparent;")
        self._primary_buttons: list[QPushButton] = []
        self._enable_dictionary_pass = True
        self._enable_kanji_pass = False
        self._latest_ocr_text: str = ""
        self._latest_selection_text: str = ""
        self._rare_format_cache: dict[str, QTextCharFormat] = {}
        self._kanji_format_cache: dict[int, QTextCharFormat] = {}
        self._clear_char_format = QTextCharFormat()
        self._clear_char_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
        self._clear_char_format.setBackground(QBrush(Qt.BrushStyle.NoBrush))
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

        self._anki_btn = QPushButton("🃏 Anki")
        self._anki_btn.setFixedHeight(28)
        self._anki_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._anki_btn.clicked.connect(self._on_anki_clicked)
        self._anki_available = False
        self._anki_last_error: str | None = None
        self._primary_buttons.append(self._anki_btn)
        ocr_header.addWidget(self._anki_btn)
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
        self._selection_placeholder = "Highlight text in the OCR pane and it will copy here automatically."
        self._sel_text.setPlaceholderText(self._selection_placeholder)
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
            self.set_selection_translation(selected)
            self.selection_changed.emit(selected)
        else:
            self._sel_text.setPlaceholderText(self._selection_placeholder)
            self._sel_text.clear()
            self._latest_selection_text = ""
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
        normalized = text or ""
        self._latest_ocr_text = normalized
        self._ocr_text.setPlainText(normalized)
        self._apply_token_highlighting(self._ocr_text, normalized)

    def set_translation(self, text: str):
        self._trans_text.setPlainText(text)

    def set_selection_translation(self, text: str):
        normalized = text or ""
        self._latest_selection_text = normalized
        self._sel_text.setPlainText(normalized)
        self._apply_token_highlighting(self._sel_text, normalized)

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

    def set_enable_dictionary_pass(self, enabled: bool) -> None:
        self._enable_dictionary_pass = bool(enabled)
        self._apply_token_highlighting(self._ocr_text, self._latest_ocr_text)
        self._apply_token_highlighting(self._sel_text, self._latest_selection_text)

    def set_enable_kanji_pass(self, enabled: bool) -> None:
        self._enable_kanji_pass = bool(enabled)
        self._apply_token_highlighting(self._ocr_text, self._latest_ocr_text)
        self._apply_token_highlighting(self._sel_text, self._latest_selection_text)

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
        )
        for btn in getattr(self, '_primary_buttons', []):
            btn.setStyleSheet(style)

    def get_ocr_text(self) -> str:
        return self._ocr_text.toPlainText()

    def get_selection_text(self) -> str:
        return self._sel_text.toPlainText()

    def get_ocr_translation(self) -> str:
        return self._trans_text.toPlainText()

    def set_anki_available(self, available: bool, last_error: str | None = None) -> None:
        """Update the Anki button's availability state and tooltip."""
        self._anki_available = available
        self._anki_last_error = last_error
        self._anki_btn.setToolTip(
            "Save to Anki" if available else (last_error or "Anki is not running")
        )

    def _on_anki_clicked(self) -> None:
        """Handle Anki button click — show message box if Anki is unavailable."""
        if not self._anki_available:
            QMessageBox.information(
                self,
                "Anki Not Available",
                self._anki_last_error or "Anki is not running.\nStart Anki and try again.",
            )
            return
        self.anki_requested.emit()

    def set_anki_visible(self, visible: bool) -> None:
        """Show/hide the Anki button based on side menu configuration."""
        self._anki_btn.setVisible(visible)

    def _apply_token_highlighting(self, widget: QTextEdit, text: str) -> None:
        if not text:
            return

        cursor = widget.textCursor()
        if (
            cursor.anchor() != cursor.position()
            and QApplication.mouseButtons() & Qt.MouseButton.LeftButton
        ):
            return

        saved_pos, saved_anchor = cursor.position(), cursor.anchor()

        try:
            cursor.beginEditBlock()

            # 1. Clear only the underline/background we own
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.mergeCharFormat(self._clear_char_format)
            cursor.clearSelection()

            # 2. Dictionary pass (Pass 1) — underline only
            if self._enable_dictionary_pass and freq_annotator.ensure_freq_data_ready():
                tokens = self._build_tokens(text)
                if tokens:
                    freq_annotator.annotate_tokens(tokens)
                    if freq_annotator.FREQ_DATA_READY:
                        if logger.isEnabledFor(logging.DEBUG):
                            dump = [
                                (getattr(token, "surface", ""), getattr(token, "freq_rank", None))
                                for token in tokens[:40]
                            ]
                            logger.debug("HIGHLIGHT DUMP: %s", dump)

                        for token in tokens:
                            cursor.setPosition(token.start)
                            cursor.setPosition(token.end, QTextCursor.MoveMode.KeepAnchor)
                            rank = getattr(token, "freq_rank", None)
                            rank = self._normalize_rank(rank)
                            fmt = self._format_for_rank(rank)
                            if fmt is not None:
                                cursor.mergeCharFormat(fmt)
                        cursor.clearSelection()
                        logger.debug("Applied dictionary highlighting to %d tokens", len(tokens))
                    else:
                        logger.warning(
                            "Skipping dictionary highlighting: frequency data unavailable after annotation"
                        )
                else:
                    logger.debug("No dictionary tokens to highlight")
            elif self._enable_dictionary_pass:
                logger.warning("Skipping dictionary highlighting: frequency data unavailable")

            # 3. Kanji pass (Pass 2) — background tint only
            if self._enable_kanji_pass:
                kanji_freq.load()
                for i, ch in enumerate(text):
                    rank = kanji_freq.lookup(ch)
                    if rank is None:
                        continue
                    fmt = self._format_for_kanji_rank(rank)
                    if fmt is not None:
                        cursor.setPosition(i)
                        cursor.setPosition(i + 1, QTextCursor.MoveMode.KeepAnchor)
                        cursor.mergeCharFormat(fmt)
                cursor.clearSelection()
                logger.debug("Applied kanji background highlighting")

            cursor.endEditBlock()
        finally:
            cursor.setPosition(saved_anchor)
            cursor.setPosition(saved_pos, QTextCursor.MoveMode.KeepAnchor)
            widget.setTextCursor(cursor)

    def _normalize_rank(self, rank: object) -> int | None:
        if rank is None:
            return None
        if isinstance(rank, int):
            return rank
        if isinstance(rank, float):
            return int(rank)
        if isinstance(rank, str):
            stripped = rank.strip()
            if stripped.isdigit():
                return int(stripped)
            try:
                return int(stripped)
            except ValueError:
                return None
        try:
            return int(rank)
        except (TypeError, ValueError):
            return None

    def _build_tokens(self, text: str) -> list[_RenderToken]:
        if not text:
            return []

        freq = freq_annotator.get_freq_table()
        lemmas_by_length = freq_annotator.get_lemmas_by_length()
        max_len = min(12, max(lemmas_by_length.keys(), default=1))

        def _make_token(surface: str, start: int, end: int) -> _RenderToken:
            try:
                return _RenderToken(surface, surface, start, end)
            except TypeError:
                return _RenderToken(surface=surface, lemma=surface, start=start, end=end)

        tokens: list[_RenderToken] = []
        n = len(text)
        i = 0
        while i < n:
            matched = False
            max_candidate = min(max_len, n - i)
            for length in range(max_candidate, 0, -1):
                bucket = lemmas_by_length.get(length)
                if not bucket:
                    continue
                candidate = text[i : i + length]
                if candidate in bucket:
                    tokens.append(_make_token(candidate, i, i + length))
                    i += length
                    matched = True
                    break
            if matched:
                continue
            ch = text[i : i + 1]
            tokens.append(_make_token(ch, i, i + 1))
            i += 1

        if os.getenv("DESKTOPOCR_DEBUG"):
            preview = [(tok.surface, freq.get(tok.lemma)) for tok in tokens[:10]]
            logger.debug("TOKENIZER PREVIEW: %s", preview)

        return tokens

    def _format_for_rank(self, rank: int | None) -> QTextCharFormat | None:
        if rank is None:
            return None
        elif rank < 5000:
            key = "common"
            style = QTextCharFormat.UnderlineStyle.SingleUnderline
            color = "#0275d8"
        elif rank < 20000:
            key = "less_common"
            style = QTextCharFormat.UnderlineStyle.DotLine
            color = "#5bc0de"
        else:
            key = "rare"
            style = QTextCharFormat.UnderlineStyle.WaveUnderline
            color = "#d9534f"

        fmt = self._rare_format_cache.get(key)
        if fmt is None:
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(style)
            fmt.setUnderlineColor(QColor(color))
            self._rare_format_cache[key] = fmt
        return fmt

    def _format_for_kanji_rank(self, rank: int) -> QTextCharFormat | None:
        if rank not in (1, 2):
            return None
        fmt = self._kanji_format_cache.get(rank)
        if fmt is None:
            fmt = QTextCharFormat()
            if rank == 1:
                # Jōyō — soft blue
                fmt.setBackground(QColor(0, 120, 255, 35))
            else:
                # Jinmeiyō — soft orange
                fmt.setBackground(QColor(255, 140, 0, 35))
            self._kanji_format_cache[rank] = fmt
        return fmt
