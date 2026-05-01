"""Slide-in side menu panel — mirrors web app's #side-menu."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame, QSizePolicy, QLineEdit, QScrollArea, QComboBox,
    QDialog, QTextBrowser,
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from ui.theme import ThemePalette, DARK, LIGHT


class SideMenu(QWidget):
    """Right-edge overlay panel with toggle sections and action buttons."""

    auto_capture_changed     = pyqtSignal(bool)
    auto_copy_changed        = pyqtSignal(bool)
    auto_read_selection_changed = pyqtSignal(bool)
    dictionary_pass_changed  = pyqtSignal(bool)
    kanji_pass_changed       = pyqtSignal(bool)
    history_visible_changed  = pyqtSignal(bool)
    preview_visible_changed  = pyqtSignal(bool)
    ocr_canvas_visible_changed = pyqtSignal(bool)
    vn_cleaner_changed       = pyqtSignal(bool)
    diff_threshold_changed   = pyqtSignal(float)
    text_size_changed        = pyqtSignal(str)
    tray_height_changed      = pyqtSignal(str)
    theme_changed            = pyqtSignal(str)  # "auto" | "dark" | "light"
    translation_enabled_changed  = pyqtSignal(bool)
    translation_backend_changed  = pyqtSignal(str)  # "auto" | "deepl" | "libre"
    auto_translate_selection_changed = pyqtSignal(bool)
    openai_validator_enabled_changed = pyqtSignal(bool)
    openai_api_key_changed       = pyqtSignal(str)
    openai_model_changed         = pyqtSignal(str)
    deepseek_validator_enabled_changed = pyqtSignal(bool)
    deepseek_api_key_changed     = pyqtSignal(str)
    deepseek_model_changed       = pyqtSignal(str)
    google_vision_enabled_changed = pyqtSignal(bool)
    google_vision_api_key_changed = pyqtSignal(str)
    # Anki integration signals
    anki_enabled_changed         = pyqtSignal(bool)
    anki_host_changed            = pyqtSignal(str)
    anki_port_changed            = pyqtSignal(int)
    anki_deck_changed            = pyqtSignal(str)
    anki_tags_changed            = pyqtSignal(str)
    anki_front_changed           = pyqtSignal(str)
    anki_back_changed            = pyqtSignal(str)
    anki_audio_side_changed      = pyqtSignal(str)
    anki_auto_translate_changed  = pyqtSignal(bool)
    anki_test_requested          = pyqtSignal()
    reset_requested          = pyqtSignal()
    hide_requested           = pyqtSignal()
    user_guide_requested     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)
        self.setObjectName("SideMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self._auto_read_toggle: tuple[QPushButton, QPushButton] | None = None
        self._auto_translate_toggle: tuple[QPushButton, QPushButton] | None = None
        self._openai_toggle: tuple[QPushButton, QPushButton] | None = None
        self._deepseek_toggle: tuple[QPushButton, QPushButton] | None = None
        self._google_vision_toggle: tuple[QPushButton, QPushButton] | None = None
        self._capture_preview_toggle: tuple[QPushButton, QPushButton] | None = None
        self._ocr_canvas_toggle: tuple[QPushButton, QPushButton] | None = None
        self._vn_cleaner_toggle: tuple[QPushButton, QPushButton] | None = None
        self._anki_toggle: tuple[QPushButton, QPushButton] | None = None

        # Outer layout: just holds the scroll area
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area fills the full height of the panel
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll)

        # Content widget inside scroll area
        content = QWidget()
        content.setObjectName("SideMenuContent")
        self._scroll.setWidget(content)

        # All items go into this layout
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._collapsible_panels: list[QFrame] = []
        self._collapsible_buttons: list[QPushButton] = []

        # Header
        self._header = self._create_section_header("SIDE MENU")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.installEventFilter(self)
        layout.addWidget(self._header)
        layout.addWidget(self._create_section_header("Theme"))
        theme_row = QHBoxLayout()
        self._theme_btns = {}
        for label, tid in [("Auto", "auto"), ("Dark", "dark"), ("Light", "light")]:
            btn = QPushButton(label)
            btn.setProperty("menuClass", "option-btn")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(0)
            btn.setMaximumWidth(16777215)
            btn.clicked.connect(lambda _checked, t=tid: self._on_theme_clicked(t))
            theme_row.addWidget(btn, 1)
            self._theme_btns[tid] = btn
        self._theme_btns["auto"].setChecked(True)
        layout.addLayout(theme_row)

        # Toggle sections
        self._auto_capture_toggle = self._add_toggle_section(
            layout, "Auto-Capture", self.auto_capture_changed, default=True
        )
        self._auto_copy_toggle = self._add_toggle_section(
            layout, "Auto-Copy", self.auto_copy_changed, default=False
        )
        self._auto_read_toggle = self._add_toggle_section(
            layout,
            "Auto-read Selection",
            self.auto_read_selection_changed,
            default=False,
        )
        self._history_toggle = self._add_toggle_section(layout, "History Panel",
                                 self.history_visible_changed, default=True)
        self._vn_cleaner_toggle = self._add_toggle_section(layout, "VN Text Cleaner",
                                 self.vn_cleaner_changed, default=True)

        # Text size preset (font)
        layout.addSpacing(6)
        layout.addWidget(self._create_section_header("Text Size"))
        size_row = QHBoxLayout()
        self._size_btns = {}
        for label, sid in [("S", "small"), ("M", "medium"), ("L", "large")]:
            btn = QPushButton(label)
            btn.setProperty("menuClass", "option-btn")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(0)
            btn.setMaximumWidth(16777215)
            btn.clicked.connect(lambda _checked, s=sid: self._on_text_size_clicked(s))
            size_row.addWidget(btn, 1)
            self._size_btns[sid] = btn
        self._size_btns["medium"].setChecked(True)
        layout.addLayout(size_row)

        # Text area size preset (tray height)
        layout.addWidget(self._create_section_header("Text Area Size"))
        tray_row = QHBoxLayout()
        self._tray_size_btns = {}
        for label, sid in [("S", "small"), ("M", "medium"), ("L", "large")]:
            btn = QPushButton(label)
            btn.setProperty("menuClass", "option-btn")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(0)
            btn.setMaximumWidth(16777215)
            btn.clicked.connect(lambda _checked, s=sid: self._on_tray_height_clicked(s))
            tray_row.addWidget(btn, 1)
            self._tray_size_btns[sid] = btn
        self._tray_size_btns["medium"].setChecked(True)
        layout.addLayout(tray_row)

        self._text_highlights_btn, th_layout = self._create_collapsible_group(
            "Text Highlights", layout, default_open=False
        )
        self._text_highlights_panel = th_layout.parentWidget()

        self._dictionary_pass_toggle = self._add_toggle_section(
            th_layout,
            "Dictionary Pass",
            self.dictionary_pass_changed,
            default=True,
            help_text=(
                "Shows how common each word is. "
                "Solid = very common, dotted = less common, red wave = rare, none = unknown. "
                "Inflected forms inherit the base dictionary lemma."
            ),
            help_html=(
                "<h3 style='margin-top:0;color:#7dd3fc;'>Dictionary Frequency Underlines</h3>"
                "<p>Words are underlined based on how common they are in everyday Japanese:</p>"
                "<ul>"
                "<li><b>Solid underline</b> — very common word</li>"
                "<li><b>Dotted underline</b> — less common word</li>"
                "<li><b>Red wave underline</b> — rare word</li>"
                "<li><b>No underline</b> — not in dictionary / unknown</li>"
                "</ul>"
                "<p>Inflected forms automatically inherit the rank of their base dictionary "
                "lemma (e.g., <code>行かない</code> → <code>行く</code>).</p>"
            ),
        )
        self._kanji_pass_toggle = self._add_toggle_section(
            th_layout,
            "Kanji Pass",
            self.kanji_pass_changed,
            default=False,
            help_text=(
                "Highlights individual kanji by category (Jōyō / Jinmeiyō). "
                "This layer is additive and does not overwrite dictionary underlines."
            ),
            help_html=(
                "<h3 style='margin-top:0;color:#7dd3fc;'>Kanji Category Backgrounds</h3>"
                "<p>Individual kanji receive a soft background tint based on category:</p>"
                "<ul>"
                "<li><b>Jōyō kanji</b> — standard everyday kanji taught in school</li>"
                "<li><b>Jinmeiyō kanji</b> — name-use kanji</li>"
                "</ul>"
                "<p>This layer is purely visual and never overwrites dictionary "
                "frequency underlines. Both passes stack safely.</p>"
            ),
        )

        # --- Translation section ---
        self._translation_toggle_btn, translation_layout = self._create_collapsible_group(
            "Translation Options", layout, default_open=False
        )
        translation_layout.addWidget(self._create_section_header("Translation"))
        self._translation_enabled_toggle = self._add_toggle_section(
            translation_layout, "Enable Translation",
            self.translation_enabled_changed, default=True
        )
        self._auto_translate_toggle = self._add_toggle_section(
            translation_layout,
            "Auto-translate Selection",
            self.auto_translate_selection_changed,
            default=False,
        )

        translation_layout.addWidget(self._create_section_header("Backend"))
        backend_row = QHBoxLayout()
        self._backend_btns: dict[str, QPushButton] = {}
        for label, bid in [("Auto", "auto"), ("DeepL", "deepl"), ("Google", "google")]:
            btn = QPushButton(label)
            btn.setProperty("menuClass", "option-btn")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(0)
            btn.setMaximumWidth(16777215)
            btn.clicked.connect(
                lambda _checked, b=bid: self._on_translation_backend_clicked(b)
            )
            backend_row.addWidget(btn, 1)
            self._backend_btns[bid] = btn
        self._backend_btns["auto"].setChecked(True)
        translation_layout.addLayout(backend_row)

        # AI Enhancements
        self._ai_toggle_btn, ai_layout = self._create_collapsible_group(
            "AI Enhancements", layout, default_open=False
        )

        ai_layout.addWidget(self._create_section_header("OpenAI Validator"))
        self._openai_toggle = self._add_toggle_section(
            ai_layout, "OpenAI Validator",
            self.openai_validator_enabled_changed,
            default=False
        )
        
        self._openai_details = QWidget()
        openai_form = QVBoxLayout(self._openai_details)
        openai_form.setContentsMargins(0, 0, 0, 0)
        openai_form.setSpacing(6)

        openai_form.addWidget(self._create_section_header("OpenAI API Key"))
        self._openai_api_key_edit = QLineEdit()
        self._openai_api_key_edit.setPlaceholderText("sk-...")
        self._openai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_api_key_edit.editingFinished.connect(
            lambda: self.openai_api_key_changed.emit(self._openai_api_key_edit.text().strip())
        )
        openai_form.addWidget(self._openai_api_key_edit)

        openai_form.addWidget(self._create_section_header("OpenAI Model"))
        self._openai_model_combo = QComboBox()
        self._openai_model_combo.addItems(["gpt-4o-mini", "gpt-4o"])
        self._openai_model_combo.currentTextChanged.connect(self.openai_model_changed.emit)
        openai_form.addWidget(self._openai_model_combo)

        self._openai_usage_label = QLabel("Session usage: 0 chars")
        self._openai_usage_label.setStyleSheet("color: #888888; font-size: 11px;")
        openai_form.addWidget(self._openai_usage_label)

        self._openai_details.setVisible(False)
        self.openai_validator_enabled_changed.connect(self._openai_details.setVisible)
        ai_layout.addWidget(self._openai_details)

        ai_layout.addWidget(self._create_section_header("DeepSeek Validator (Budget Mode)"))
        self._deepseek_toggle = self._add_toggle_section(
            ai_layout,
            "Enable DeepSeek",
            self.deepseek_validator_enabled_changed,
            default=False,
        )
        self._deepseek_details = QWidget()
        deepseek_form = QVBoxLayout(self._deepseek_details)
        deepseek_form.setContentsMargins(0, 0, 0, 0)
        deepseek_form.setSpacing(6)

        deepseek_desc = QLabel(
            "Uses DeepSeek for low-cost AI cleanup. Text is sent to DeepSeek's servers."
        )
        deepseek_desc.setWordWrap(True)
        deepseek_desc.setStyleSheet("color: #a0a0aa; font-size: 11px; margin-top: 0;")
        deepseek_form.addWidget(deepseek_desc)

        deepseek_form.addWidget(self._create_section_header("DeepSeek API Key"))
        self._deepseek_api_key_edit = QLineEdit()
        self._deepseek_api_key_edit.setPlaceholderText("ds-...")
        self._deepseek_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._deepseek_api_key_edit.editingFinished.connect(
            lambda: self.deepseek_api_key_changed.emit(
                self._deepseek_api_key_edit.text().strip()
            )
        )
        deepseek_form.addWidget(self._deepseek_api_key_edit)

        deepseek_form.addWidget(self._create_section_header("DeepSeek Model"))
        self._deepseek_model_combo = QComboBox()
        self._deepseek_model_combo.addItems(["deepseek-chat"])
        self._deepseek_model_combo.currentTextChanged.connect(
            self.deepseek_model_changed.emit
        )
        deepseek_form.addWidget(self._deepseek_model_combo)

        self._deepseek_details.setVisible(False)
        self.deepseek_validator_enabled_changed.connect(self._deepseek_details.setVisible)
        ai_layout.addWidget(self._deepseek_details)

        ai_layout.addWidget(self._create_section_header("Cloud OCR (Google Vision)"))
        self._google_vision_toggle = self._add_toggle_section(
            ai_layout,
            "Enable Cloud OCR",
            self.google_vision_enabled_changed,
            default=False,
        )
        self._google_vision_details = QWidget()
        cloud_form = QVBoxLayout(self._google_vision_details)
        cloud_form.setContentsMargins(0, 0, 0, 0)
        cloud_form.setSpacing(6)

        desc = QLabel(
            "Bring Your Own Key – data only leaves your machine when enabled."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a0a0aa; font-size: 11px; margin-top: 0;")
        cloud_form.addWidget(desc)

        cloud_form.addWidget(self._create_section_header("Google Vision API Key"))
        self._google_vision_key_edit = QLineEdit()
        self._google_vision_key_edit.setPlaceholderText("AIza...")
        self._google_vision_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._google_vision_key_edit.editingFinished.connect(
            lambda: self.google_vision_api_key_changed.emit(
                self._google_vision_key_edit.text().strip()
            )
        )
        cloud_form.addWidget(self._google_vision_key_edit)

        self._google_vision_details.setVisible(False)
        self.google_vision_enabled_changed.connect(self._google_vision_details.setVisible)
        ai_layout.addWidget(self._google_vision_details)

        # --- Anki Integration section ---
        self._anki_toggle_btn, anki_layout = self._create_collapsible_group(
            "Anki Integration", layout, default_open=False
        )

        anki_layout.addWidget(self._create_section_header("Anki"))
        _anki_help_html = (
            "<h3 style='margin-top:0;color:#7dd3fc;'>Anki Integration</h3>"
            "<p>DesktopOCR can save OCR results directly to <strong>Anki</strong> "
            "flashcards via the <strong>AnkiConnect</strong> add-on.</p>"
            "<p><strong>Prerequisites:</strong></p>"
            "<ul>"
            "<li><strong>Anki</strong> must be installed <strong>and running</strong>.</li>"
            "<li>Install <strong>AnkiConnect</strong> (Tools → Add-ons → Get Add-ons"
            " → code <code>2055492159</code>). Restart Anki after installing.</li>"
            "</ul>"
            "<p><strong>How it works:</strong></p>"
            "<ol>"
            "<li>Enable Anki in this menu.</li>"
            "<li>The 🃏 Anki button lights up once AnkiConnect is detected (polled every 30s).</li>"
            "<li>Click 🃏 to send OCR text, translation, screenshot, and audio to a new card.</li>"
            "</ol>"
            "<p><strong>Settings:</strong></p>"
            "<ul>"
            "<li><strong>Host / Port</strong> — AnkiConnect runs on localhost:8765 by default.</li>"
            "<li><strong>Deck Name</strong> — Saved cards go here. Created automatically.</li>"
            "<li><strong>Tags</strong> — Comma-separated tags on each card (default: japanese, vn).</li>"
            "<li><strong>Front / Back Templates</strong> — Which content appears on each side.</li>"
            "<li><strong>Audio Side</strong> — Attach TTS audio to front, back, or both.</li>"
            "<li><strong>Auto-translate</strong> — Silently fetches translations when you click 🃏.</li>"
            "</ul>"
            "<p style='color:#fbbf24;font-weight:bold;'>"
            "⚠ Make sure Anki is running. AnkiConnect only responds while Anki is open.</p>"
        )
        self._anki_toggle = self._add_toggle_section(
            anki_layout, "Enable Anki",
            self.anki_enabled_changed, default=False,
            help_text="Click for AnkiConnect setup & usage instructions",
            help_html=_anki_help_html,
        )

        anki_layout.addWidget(self._create_section_header("Host"))
        self._anki_host_edit = QLineEdit()
        self._anki_host_edit.setPlaceholderText("localhost")
        self._anki_host_edit.editingFinished.connect(
            lambda: self.anki_host_changed.emit(self._anki_host_edit.text().strip())
        )
        anki_layout.addWidget(self._anki_host_edit)

        anki_layout.addWidget(self._create_section_header("Port"))
        self._anki_port_edit = QLineEdit()
        self._anki_port_edit.setPlaceholderText("8765")
        self._anki_port_edit.editingFinished.connect(
            lambda: self._on_anki_port_finished()
        )
        anki_layout.addWidget(self._anki_port_edit)

        anki_layout.addWidget(self._create_section_header("Deck Name"))
        self._anki_deck_edit = QLineEdit()
        self._anki_deck_edit.setPlaceholderText("DesktopOCR")
        self._anki_deck_edit.editingFinished.connect(
            lambda: self.anki_deck_changed.emit(self._anki_deck_edit.text().strip())
        )
        anki_layout.addWidget(self._anki_deck_edit)

        anki_layout.addWidget(self._create_section_header("Tags"))
        self._anki_tags_edit = QLineEdit()
        self._anki_tags_edit.setPlaceholderText("japanese, vn")
        self._anki_tags_edit.editingFinished.connect(
            lambda: self.anki_tags_changed.emit(self._anki_tags_edit.text().strip())
        )
        anki_layout.addWidget(self._anki_tags_edit)

        # Test Connection button
        _test_btn = QPushButton("Test Connection")
        _test_btn.setProperty("menuClass", "option-btn")
        _test_btn.clicked.connect(lambda: self.anki_test_requested.emit())
        anki_layout.addWidget(_test_btn)

        anki_layout.addWidget(self._create_section_header("Front Template"))
        self._anki_front_combo = QComboBox()
        self._anki_front_combo.addItems(["screenshot", "screenshot_selection", "selection_only"])
        self._anki_front_combo.currentTextChanged.connect(self.anki_front_changed.emit)
        anki_layout.addWidget(self._anki_front_combo)

        anki_layout.addWidget(self._create_section_header("Back Template"))
        self._anki_back_combo = QComboBox()
        self._anki_back_combo.addItems(["full_with_context", "selection_only", "full_only"])
        self._anki_back_combo.currentTextChanged.connect(self.anki_back_changed.emit)
        anki_layout.addWidget(self._anki_back_combo)

        anki_layout.addWidget(self._create_section_header("Audio Side"))
        self._anki_audio_side_combo = QComboBox()
        self._anki_audio_side_combo.addItems(["front", "back", "both"])
        self._anki_audio_side_combo.currentTextChanged.connect(self.anki_audio_side_changed.emit)
        anki_layout.addWidget(self._anki_audio_side_combo)

        self._anki_auto_translate_toggle = self._add_toggle_section(
            anki_layout,
            "Auto-translate for Anki",
            self.anki_auto_translate_changed,
            default=True,
        )

        # Advanced settings toggle (collapsible)
        self._advanced_toggle_btn = QPushButton("Advanced Settings")
        self._advanced_toggle_btn.setProperty("menuClass", "option-btn")
        self._advanced_toggle_btn.setCheckable(True)
        self._advanced_toggle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._advanced_toggle_btn.setMinimumWidth(0)
        self._advanced_toggle_btn.setMaximumWidth(16777215)
        layout.addWidget(self._advanced_toggle_btn)

        self._advanced_panel = QWidget()
        adv_panel_layout = QVBoxLayout(self._advanced_panel)
        adv_panel_layout.setContentsMargins(0, 4, 0, 0)
        adv_panel_layout.setSpacing(6)
        adv_panel_layout.addWidget(self._create_section_header("Diff Threshold"))
        self._threshold_label = QLabel("8")
        self._threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self._threshold_slider.setMinimum(1)
        self._threshold_slider.setMaximum(30)
        self._threshold_slider.setValue(8)
        self._threshold_slider.valueChanged.connect(
            lambda v: (
                self._threshold_label.setText(str(v)),
                self.diff_threshold_changed.emit(float(v)),
            )
        )
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(self._threshold_slider)
        threshold_row.addWidget(self._threshold_label)
        adv_panel_layout.addLayout(threshold_row)
        self._capture_preview_toggle = self._add_toggle_section(
            adv_panel_layout,
            "Capture Preview",
            self.preview_visible_changed,
            default=True,
        )
        self._ocr_canvas_toggle = self._add_toggle_section(
            adv_panel_layout,
            "OCR Canvas (Debug)",
            self.ocr_canvas_visible_changed,
            default=False,
        )
        layout.addWidget(self._advanced_panel)
        self._advanced_panel.setVisible(False)
        self._collapsible_buttons.append(self._advanced_toggle_btn)
        self._collapsible_panels.append(self._advanced_panel)

        self._advanced_toggle_btn.clicked.connect(
            lambda checked: self._set_advanced_visible(bool(checked))
        )
        self._set_advanced_visible(False)

        # Action buttons
        self._user_guide_btn = QPushButton("User Guide")
        self._user_guide_btn.setProperty("menuClass", "option-btn")
        self._user_guide_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._user_guide_btn.setMinimumWidth(0)
        self._user_guide_btn.setMaximumWidth(16777215)
        self._user_guide_btn.clicked.connect(self.user_guide_requested.emit)
        layout.addWidget(self._user_guide_btn)

        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._reset_btn.setMinimumWidth(0)
        self._reset_btn.setMaximumWidth(16777215)
        self._reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(self._reset_btn)

        layout.addStretch()

        # Apply initial stylesheet
        self._apply_base_style()

    def eventFilter(self, obj, event):
        if obj is self._header and event.type() == QEvent.Type.MouseButtonRelease:
            self.hide_requested.emit()
            return True
        return super().eventFilter(obj, event)

    def _apply_base_style(self):
        pal = getattr(self, '_pal', None)
        is_dark = not pal or pal.is_dark
        bg = pal.panel if pal else "#0d0d10"
        border = pal.border if pal else "#1f1f23"
        text = pal.text if pal else "#ffffff"
        text_dim = pal.text_dim if pal else "#8a8a93"
        accent = pal.accent if pal else "#10b981"
        btn_bg = "#1a1a1f" if is_dark else "#f1f5f9"
        btn_border = "#2a2a2f" if is_dark else "#cbd5e1"
        btn_hover_border = "#3a3a3f" if is_dark else "#94a3b8"
        btn_hover_bg = "rgba(255,255,255,0.08)" if is_dark else "rgba(0,0,0,0.06)"
        groove = "#2a2a2f" if is_dark else "#e2e8f0"
        panel_bg = (
            f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {bg}, stop:1 {border})"
            if is_dark else bg
        )
        for p in getattr(self, "_collapsible_panels", []):
            p.setStyleSheet(
                f"QFrame {{ background: {btn_bg}; border: none; "
                f"border-radius: 6px; margin-top: 2px; margin-bottom: 6px; }}"
            )

        self.setStyleSheet(f"""
            #SideMenu {{
                background: {panel_bg};
                border-right: 1px solid {border};
            }}

            #SideMenu QLabel {{
                background: transparent;
                color: {text_dim};
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.5px;
                margin-top: 8px;
                margin-bottom: 2px;
            }}

            #SideMenu QPushButton[menuClass="option-btn"] {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {btn_border};
                border-radius: 8px;
                padding: 4px 6px;
                min-height: 28px;
                font-size: 13px;
                font-weight: 600;
                width: 50%;
            }}
            #SideMenu QPushButton[menuClass="option-btn"]:checked {{
                background: {accent};
                color: #ffffff;
                border-color: {accent};
            }}
            #SideMenu QPushButton[menuClass="option-btn"]:hover {{
                border-color: {btn_hover_border};
                background: {btn_hover_bg};
            }}

            #SideMenu QPushButton {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {btn_border};
                border-radius: 8px;
                padding: 4px 6px;
                min-height: 28px;
                font-size: 13px;
            }}
            #SideMenu QPushButton:hover {{
                border-color: {accent};
            }}

            #SideMenu QPushButton[menuClass="help-btn"] {{
                background: {btn_bg};
                color: {text_dim};
                border: 1px solid {btn_border};
                border-radius: 14px;
                padding: 0;
                min-height: 28px;
                max-width: 28px;
                max-height: 28px;
                font-size: 14px;
                font-weight: 700;
            }}
            #SideMenu QPushButton[menuClass="help-btn"]:hover {{
                background: {btn_hover_bg};
                border-color: {accent};
                color: {accent};
            }}

            #SideMenu QSlider::groove:horizontal {{
                background: {groove};
                height: 5px;
                border-radius: 3px;
            }}
            #SideMenu QSlider::handle:horizontal {{
                background: {accent};
                width: 16px;
                height: 16px;
                border-radius: 8px;
                margin: -6px 0;
            }}

            #SideMenu QLineEdit {{
                background: {btn_bg};
                color: {text_dim};
                border: 1px solid {btn_border};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
            }}

            /* Scroll area transparency - let SideMenu gradient show through */
            #SideMenu QScrollArea {{
                background: transparent;
                border: none;
            }}
            #SideMenu QScrollArea QWidget {{
                background: transparent;
            }}
            #SideMenuContent {{
                background: transparent;
            }}

            /* Slim themed scrollbar */
            #SideMenu QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            #SideMenu QScrollBar::handle:vertical {{
                background: {btn_border};
                border-radius: 3px;
                min-height: 30px;
            }}
            #SideMenu QScrollBar::handle:vertical:hover {{
                background: {accent};
            }}
            #SideMenu QScrollBar::add-line:vertical,
            #SideMenu QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

    def _on_text_size_clicked(self, size_id: str):
        for sid, btn in self._size_btns.items():
            btn.setChecked(sid == size_id)
        self.text_size_changed.emit(size_id)

    def _on_tray_height_clicked(self, size_id: str):
        for sid, btn in self._tray_size_btns.items():
            btn.setChecked(sid == size_id)
        self.tray_height_changed.emit(size_id)

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        pal = getattr(self, '_pal', None)
        border = pal.border if pal else "#1f1f23"
        line.setStyleSheet(f"background: {border}; max-height: 1px; margin-top: 12px; margin-bottom: 12px; opacity: 0.5;")
        return line

    def _create_section_header(self, text: str) -> QLabel:
        header = QLabel(text)
        header.setObjectName("section_header")
        header.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        header.setStyleSheet("background: transparent; border: none;")
        return header

    def _create_collapsible_group(
        self,
        title: str,
        parent_layout: QVBoxLayout,
        *,
        default_open: bool = False,
    ) -> tuple[QPushButton, QVBoxLayout]:
        btn = QPushButton(title)
        btn.setProperty("menuClass", "option-btn")
        btn.setCheckable(True)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setMinimumWidth(0)
        btn.setMaximumWidth(16777215)
        parent_layout.addWidget(btn)

        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.NoFrame)
        panel.setAutoFillBackground(True)
        self._collapsible_panels.append(panel)
        self._collapsible_buttons.append(btn)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 4, 0, 0)
        panel_layout.setSpacing(6)
        parent_layout.addWidget(panel)

        panel.setVisible(default_open)
        btn.setChecked(default_open)
        btn.clicked.connect(lambda checked, target=panel: target.setVisible(checked))
        return btn, panel_layout

    def _on_theme_clicked(self, theme_id: str):
        for tid, btn in self._theme_btns.items():
            btn.setChecked(tid == theme_id)
        self.theme_changed.emit(theme_id)

    def set_theme(self, pal: ThemePalette):
        self._pal = pal
        self._apply_base_style()
        # Header gets full brightness text; override the dimmed QLabel rule
        self._header.setStyleSheet(
            f"color: {pal.text}; font-size: 18px; font-weight: 800; "
            f"letter-spacing: 1px; background: transparent; margin-top: 0;"
        )
        # Reset button gets panic color
        self._reset_btn.setStyleSheet(
            f"color: {pal.panic}; background: transparent; "
            f"border: 1px solid {pal.panic}; border-radius: 8px;"
        )

    def _on_reset(self):
        # Reset toggles to their defaults
        self._size_btns["medium"].setChecked(True)
        for sid, btn in self._size_btns.items():
            if sid != "medium":
                btn.setChecked(False)
        self.text_size_changed.emit("medium")
        self._tray_size_btns["medium"].setChecked(True)
        for sid, btn in self._tray_size_btns.items():
            if sid != "medium":
                btn.setChecked(False)
        self.tray_height_changed.emit("medium")
        self._theme_btns["auto"].setChecked(True)
        for tid, btn in self._theme_btns.items():
            if tid != "auto":
                btn.setChecked(False)
        self.theme_changed.emit("auto")
        self.set_auto_read_selection(False)
        self.set_auto_translate_selection(False)
        self.set_enable_dictionary_pass(True, emit_signal=True)
        self.set_enable_kanji_pass(False, emit_signal=True)
        self.set_preview_visible(True, emit_signal=True)
        self._set_advanced_visible(False)
        self.set_ocr_canvas_visible(False, emit_signal=True)
        # Reset Anki settings
        self.set_anki_enabled(False, emit_signal=True)
        self.set_anki_host("localhost")
        self.set_anki_port(8765)
        self.set_anki_deck("DesktopOCR")
        self.set_anki_tags("japanese, vn")
        self.set_anki_front("screenshot")
        self.set_anki_back("full_with_context")
        self.set_anki_audio_side("front")
        self.set_anki_auto_translate(True, emit_signal=True)
        self.reset_requested.emit()

    def _add_toggle_section(self, layout, title: str,
                           signal: pyqtSignal, default: bool,
                           help_text: str | None = None,
                           help_html: str | None = None):
        header = self._create_section_header(title)
        header.setContentsMargins(0, 4, 0, 2)

        if help_text:
            header_row = QHBoxLayout()
            header_row.setContentsMargins(0, 0, 0, 0)
            header_row.setSpacing(4)
            header_row.addWidget(header)
            header_row.addStretch(1)
            help_btn = QPushButton("?")
            help_btn.setProperty("menuClass", "help-btn")
            help_btn.setToolTip(help_text)
            help_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            help_btn.setFixedSize(28, 28)
            if help_html:
                help_btn.clicked.connect(
                    lambda _checked, t=title, h=help_html: self._show_help_dialog(t, h)
                )
            header_row.addWidget(help_btn, 0)
            layout.addLayout(header_row)
        else:
            layout.addWidget(header)

        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(4)
        on_btn = QPushButton("On")
        off_btn = QPushButton("Off")
        on_btn.setProperty("menuClass", "option-btn")
        off_btn.setProperty("menuClass", "option-btn")
        on_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        on_btn.setMinimumWidth(0)
        on_btn.setMaximumWidth(16777215)
        off_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        off_btn.setMinimumWidth(0)
        off_btn.setMaximumWidth(16777215)
        on_btn.setCheckable(True)
        off_btn.setCheckable(True)
        on_btn.setChecked(default)
        off_btn.setChecked(not default)

        def _on_clicked():
            on_btn.setChecked(True)
            off_btn.setChecked(False)
            signal.emit(True)

        def _off_clicked():
            on_btn.setChecked(False)
            off_btn.setChecked(True)
            signal.emit(False)

        on_btn.clicked.connect(_on_clicked)
        off_btn.clicked.connect(_off_clicked)
        row.addWidget(on_btn, 1)
        row.addWidget(off_btn, 1)

        layout.addLayout(row)
        return on_btn, off_btn

    def _set_toggle_state(self, pair: tuple[QPushButton, QPushButton] | None, enabled: bool) -> None:
        if not pair:
            return
        on_btn, off_btn = pair
        for btn, should_check in ((on_btn, enabled), (off_btn, not enabled)):
            if btn.isChecked() == should_check:
                continue
            block = btn.blockSignals(True)
            btn.setChecked(should_check)
            btn.blockSignals(block)

    def collapse_all_groups(self) -> None:
        for btn, panel in zip(self._collapsible_buttons, self._collapsible_panels):
            block = btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(block)
            panel.setVisible(False)

    def set_auto_read_selection(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._auto_read_toggle, enabled)
        if emit_signal:
            self.auto_read_selection_changed.emit(enabled)

    def _show_help_dialog(self, title: str, html: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(420, 260)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        browser = QTextBrowser()
        pal = getattr(self, "_pal", None)
        bg = pal.panel if pal else "#14161c"
        text = pal.text if pal else "#f7f8fb"
        accent = pal.accent if pal else "#10b981"
        browser.setStyleSheet(
            f"QTextBrowser {{ background: {bg}; color: {text}; border: none; }}"
        )
        browser.setHtml(
            f"<html><body style='font-family:Segoe UI,Roboto,Noto Sans,sans-serif;"
            f"font-size:14px;line-height:1.6;color:{text};background:{bg};padding:8px;'>"
            f"<style>a{{color:{accent};}}</style>{html}</body></html>"
        )
        v.addWidget(browser, 1)
        btn = QPushButton("Close")
        btn.setProperty("menuClass", "option-btn")
        btn.clicked.connect(dlg.accept)
        v.addWidget(btn)
        dlg.exec()

    def set_history_visible(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._history_toggle, enabled)
        if emit_signal:
            self.history_visible_changed.emit(enabled)

    def set_auto_capture(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._auto_capture_toggle, enabled)
        if emit_signal:
            self.auto_capture_changed.emit(enabled)

    def set_auto_copy(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._auto_copy_toggle, enabled)
        if emit_signal:
            self.auto_copy_changed.emit(enabled)

    def set_translation_backend(self, backend_id: str, *, emit_signal: bool = False) -> None:
        if backend_id not in self._backend_btns:
            backend_id = "auto"  # safe fallback — matches DEFAULT_SETTINGS
        for bid, btn in self._backend_btns.items():
            btn.setChecked(bid == backend_id)
        # LibreTranslate is hidden for now, so URL field stays hidden
        if emit_signal:
            self.translation_backend_changed.emit(backend_id)

    def set_auto_translate_selection(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._auto_translate_toggle, enabled)
        if emit_signal:
            self.auto_translate_selection_changed.emit(enabled)

    def set_translation_enabled(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._translation_enabled_toggle, enabled)
        if emit_signal:
            self.translation_enabled_changed.emit(enabled)

    def set_vn_cleaner(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._vn_cleaner_toggle, enabled)
        if emit_signal:
            self.vn_cleaner_changed.emit(enabled)

    def set_diff_threshold(self, value: float, *, emit_signal: bool = False) -> None:
        if not hasattr(self, "_threshold_slider") or not hasattr(self, "_threshold_label"):
            return

        old_block = self._threshold_slider.blockSignals(True)
        try:
            int_value = int(round(value))
            self._threshold_slider.setValue(int_value)
            self._threshold_label.setText(str(int_value))
        finally:
            self._threshold_slider.blockSignals(old_block)

        if emit_signal:
            self.diff_threshold_changed.emit(float(int_value))

    def set_enable_dictionary_pass(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._dictionary_pass_toggle, enabled)
        if emit_signal:
            self.dictionary_pass_changed.emit(enabled)

    def set_enable_kanji_pass(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._kanji_pass_toggle, enabled)
        if emit_signal:
            self.kanji_pass_changed.emit(enabled)

    def set_openai_validator_enabled(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._openai_toggle, enabled)
        if hasattr(self, "_openai_details"):
            self._openai_details.setVisible(enabled)
        if emit_signal:
            self.openai_validator_enabled_changed.emit(enabled)

    def set_openai_api_key(self, key: str) -> None:
        if hasattr(self, "_openai_api_key_edit"):
            self._openai_api_key_edit.setText(key or "")

    def set_openai_model(self, model: str) -> None:
        if not hasattr(self, "_openai_model_combo"):
            return
        combo = self._openai_model_combo
        block = combo.blockSignals(True)
        idx = combo.findText(model)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(block)

    def set_deepseek_validator_enabled(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._deepseek_toggle, enabled)
        if hasattr(self, "_deepseek_details"):
            self._deepseek_details.setVisible(enabled)
        if emit_signal:
            self.deepseek_validator_enabled_changed.emit(enabled)

    def set_deepseek_api_key(self, key: str) -> None:
        if hasattr(self, "_deepseek_api_key_edit"):
            self._deepseek_api_key_edit.setText(key or "")

    def set_deepseek_model(self, model: str) -> None:
        if not hasattr(self, "_deepseek_model_combo"):
            return
        combo = self._deepseek_model_combo
        block = combo.blockSignals(True)
        idx = combo.findText(model)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(block)

    def set_google_vision_enabled(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._google_vision_toggle, enabled)
        if hasattr(self, "_google_vision_details"):
            self._google_vision_details.setVisible(enabled)
        if emit_signal:
            self.google_vision_enabled_changed.emit(enabled)

    def set_google_vision_api_key(self, key: str) -> None:
        if hasattr(self, "_google_vision_key_edit"):
            self._google_vision_key_edit.setText(key or "")

    def set_ocr_canvas_visible(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._ocr_canvas_toggle, enabled)
        if emit_signal:
            self.ocr_canvas_visible_changed.emit(enabled)

    def set_preview_visible(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._capture_preview_toggle, enabled)
        if emit_signal:
            self.preview_visible_changed.emit(enabled)

    def set_theme_id(self, theme_id: str, *, emit_signal: bool = False) -> None:
        if theme_id not in self._theme_btns:
            return
        for tid, btn in self._theme_btns.items():
            btn.setChecked(tid == theme_id)
        if emit_signal:
            self.theme_changed.emit(theme_id)

    def set_text_size(self, size_id: str, *, emit_signal: bool = False) -> None:
        if size_id not in self._size_btns:
            return
        for sid, btn in self._size_btns.items():
            btn.setChecked(sid == size_id)
        if emit_signal:
            self.text_size_changed.emit(size_id)

    def set_tray_height(self, size_id: str, *, emit_signal: bool = False) -> None:
        if size_id not in self._tray_size_btns:
            return
        for sid, btn in self._tray_size_btns.items():
            btn.setChecked(sid == size_id)
        if emit_signal:
            self.tray_height_changed.emit(size_id)

    def _set_advanced_visible(self, visible: bool) -> None:
        if not hasattr(self, "_advanced_panel"):
            return
        self._advanced_toggle_btn.setChecked(visible)
        self._advanced_panel.setVisible(visible)

    def _on_translation_backend_clicked(self, backend_id: str) -> None:
        """Update backend button selection and show/hide URL field."""
        for bid, btn in self._backend_btns.items():
            btn.setChecked(bid == backend_id)
        self.translation_backend_changed.emit(backend_id)

    def update_openai_usage(self, chars: int) -> None:
        self._openai_usage_label.setText(f"Session usage: {chars} chars")

    # --- Anki setters ---

    def set_anki_enabled(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._anki_toggle, enabled)
        if emit_signal:
            self.anki_enabled_changed.emit(enabled)

    def set_anki_host(self, host: str) -> None:
        if hasattr(self, "_anki_host_edit"):
            self._anki_host_edit.setText(host or "localhost")

    def set_anki_port(self, port: int) -> None:
        if hasattr(self, "_anki_port_edit"):
            self._anki_port_edit.setText(str(port))

    def set_anki_deck(self, deck: str) -> None:
        if hasattr(self, "_anki_deck_edit"):
            self._anki_deck_edit.setText(deck or "DesktopOCR")

    def set_anki_tags(self, tags: str) -> None:
        if hasattr(self, "_anki_tags_edit"):
            self._anki_tags_edit.setText(tags or "japanese, vn")

    def set_anki_front(self, mode: str) -> None:
        if not hasattr(self, "_anki_front_combo"):
            return
        combo = self._anki_front_combo
        block = combo.blockSignals(True)
        idx = combo.findText(mode)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(block)

    def set_anki_back(self, mode: str) -> None:
        if not hasattr(self, "_anki_back_combo"):
            return
        combo = self._anki_back_combo
        block = combo.blockSignals(True)
        idx = combo.findText(mode)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(block)

    def set_anki_audio_side(self, side: str) -> None:
        if not hasattr(self, "_anki_audio_side_combo"):
            return
        combo = self._anki_audio_side_combo
        block = combo.blockSignals(True)
        idx = combo.findText(side)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(block)

    def set_anki_auto_translate(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._anki_auto_translate_toggle, enabled)
        if emit_signal:
            self.anki_auto_translate_changed.emit(enabled)

    def _on_anki_port_finished(self) -> None:
        raw = self._anki_port_edit.text().strip()
        try:
            port = int(raw)
        except (ValueError, TypeError):
            port = 8765
        self.anki_port_changed.emit(port)
