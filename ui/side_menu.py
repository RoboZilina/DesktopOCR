"""Slide-in side menu panel — mirrors web app's #side-menu."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame, QSizePolicy, QLineEdit, QScrollArea, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import ThemePalette, DARK, LIGHT


class SideMenu(QWidget):
    """Right-edge overlay panel with toggle sections and action buttons."""

    auto_capture_changed     = pyqtSignal(bool)
    auto_copy_changed        = pyqtSignal(bool)
    auto_read_selection_changed = pyqtSignal(bool)
    history_visible_changed  = pyqtSignal(bool)
    preview_visible_changed  = pyqtSignal(bool)
    vn_cleaner_changed       = pyqtSignal(bool)
    diff_threshold_changed   = pyqtSignal(float)
    text_size_changed        = pyqtSignal(str)
    tray_height_changed      = pyqtSignal(str)
    theme_changed            = pyqtSignal(str)  # "auto" | "dark" | "light"
    translation_enabled_changed  = pyqtSignal(bool)
    translation_backend_changed  = pyqtSignal(str)  # "auto" | "deepl" | "libre"
    auto_translate_selection_changed = pyqtSignal(bool)
    libre_url_changed            = pyqtSignal(str)
    openai_validator_enabled_changed = pyqtSignal(bool)
    openai_api_key_changed       = pyqtSignal(str)
    openai_model_changed         = pyqtSignal(str)
    deepseek_validator_enabled_changed = pyqtSignal(bool)
    deepseek_api_key_changed     = pyqtSignal(str)
    deepseek_model_changed       = pyqtSignal(str)
    google_vision_enabled_changed = pyqtSignal(bool)
    google_vision_api_key_changed = pyqtSignal(str)
    reset_requested          = pyqtSignal()
    hide_requested           = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)
        self.setObjectName("SideMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self._auto_read_toggle: tuple[QPushButton, QPushButton] | None = None
        self._auto_translate_toggle: tuple[QPushButton, QPushButton] | None = None

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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        self._header = QLabel("SIDE MENU")
        layout.addWidget(self._header)
        layout.addWidget(self._divider())

        # Theme toggle
        layout.addWidget(QLabel("Theme"))
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
            theme_row.addWidget(btn)
            self._theme_btns[tid] = btn
        self._theme_btns["auto"].setChecked(True)
        theme_row.addStretch()
        layout.addLayout(theme_row)
        layout.addWidget(self._divider())

        # Toggle sections
        self._add_toggle_section(layout, "Auto-Capture",
                                 self.auto_capture_changed, default=True)
        self._add_toggle_section(layout, "Auto-Copy",
                                 self.auto_copy_changed, default=False)
        self._auto_read_toggle = self._add_toggle_section(
            layout,
            "Auto-read Selection",
            self.auto_read_selection_changed,
            default=False,
        )
        self._add_toggle_section(layout, "History Panel",
                                 self.history_visible_changed, default=True)
        self._add_toggle_section(layout, "Capture Preview",
                                 self.preview_visible_changed, default=True)
        self._add_toggle_section(layout, "VN Text Cleaner",
                                 self.vn_cleaner_changed, default=True)

        # --- Translation section ---
        layout.addWidget(self._divider())
        layout.addWidget(QLabel("Translation"))
        self._add_toggle_section(
            layout, "Enable Translation",
            self.translation_enabled_changed, default=True
        )
        self._auto_translate_toggle = self._add_toggle_section(
            layout,
            "Auto-translate Selection",
            self.auto_translate_selection_changed,
            default=False,
        )

        layout.addWidget(QLabel("Backend"))
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
            backend_row.addWidget(btn)
            self._backend_btns[bid] = btn
        self._backend_btns["auto"].setChecked(True)
        backend_row.addStretch()
        layout.addLayout(backend_row)

        self._libre_url_label = QLabel("LibreTranslate URL")
        self._libre_url_label.hide()
        layout.addWidget(self._libre_url_label)
        self._libre_url_edit = QLineEdit("http://localhost:5000")
        self._libre_url_edit.hide()
        self._libre_url_edit.setPlaceholderText("http://localhost:5000")
        self._libre_url_edit.editingFinished.connect(
            lambda: self.libre_url_changed.emit(self._libre_url_edit.text().strip())
        )
        layout.addWidget(self._libre_url_edit)

        # AI Validator
        layout.addWidget(self._divider())
        self._add_toggle_section(
            layout, "AI Validator",
            self.openai_validator_enabled_changed,
            default=False
        )
        
        self._openai_details = QWidget()
        openai_form = QVBoxLayout(self._openai_details)
        openai_form.setContentsMargins(0, 0, 0, 0)
        openai_form.setSpacing(6)

        openai_form.addWidget(QLabel("OpenAI API Key"))
        self._openai_api_key_edit = QLineEdit()
        self._openai_api_key_edit.setPlaceholderText("sk-...")
        self._openai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_api_key_edit.editingFinished.connect(
            lambda: self.openai_api_key_changed.emit(self._openai_api_key_edit.text().strip())
        )
        openai_form.addWidget(self._openai_api_key_edit)

        openai_form.addWidget(QLabel("OpenAI Model"))
        self._openai_model_combo = QComboBox()
        self._openai_model_combo.addItems(["gpt-4o-mini", "gpt-4o"])
        self._openai_model_combo.currentTextChanged.connect(self.openai_model_changed.emit)
        openai_form.addWidget(self._openai_model_combo)

        self._openai_usage_label = QLabel("Session usage: 0 chars")
        self._openai_usage_label.setStyleSheet("color: #888888; font-size: 11px;")
        openai_form.addWidget(self._openai_usage_label)

        self._openai_details.setVisible(False)
        self.openai_validator_enabled_changed.connect(self._openai_details.setVisible)
        layout.addWidget(self._openai_details)

        # DeepSeek Validator (Budget Mode)
        layout.addWidget(self._divider())
        layout.addWidget(QLabel("DeepSeek Validator (Budget Mode)"))
        self._add_toggle_section(
            layout,
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

        deepseek_form.addWidget(QLabel("DeepSeek API Key"))
        self._deepseek_api_key_edit = QLineEdit()
        self._deepseek_api_key_edit.setPlaceholderText("ds-...")
        self._deepseek_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._deepseek_api_key_edit.editingFinished.connect(
            lambda: self.deepseek_api_key_changed.emit(
                self._deepseek_api_key_edit.text().strip()
            )
        )
        deepseek_form.addWidget(self._deepseek_api_key_edit)

        deepseek_form.addWidget(QLabel("DeepSeek Model"))
        self._deepseek_model_combo = QComboBox()
        self._deepseek_model_combo.addItems(["deepseek-chat"])
        self._deepseek_model_combo.currentTextChanged.connect(
            self.deepseek_model_changed.emit
        )
        deepseek_form.addWidget(self._deepseek_model_combo)

        self._deepseek_details.setVisible(False)
        self.deepseek_validator_enabled_changed.connect(self._deepseek_details.setVisible)
        layout.addWidget(self._deepseek_details)

        # Cloud OCR (Google Vision)
        layout.addWidget(self._divider())
        layout.addWidget(QLabel("Cloud OCR (Google Vision)"))
        self._add_toggle_section(
            layout,
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

        cloud_form.addWidget(QLabel("Google Vision API Key"))
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
        layout.addWidget(self._google_vision_details)

        # Text size preset (font)
        layout.addWidget(self._divider())
        layout.addWidget(QLabel("Text Size"))
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
            size_row.addWidget(btn)
            self._size_btns[sid] = btn
        self._size_btns["medium"].setChecked(True)
        size_row.addStretch()
        layout.addLayout(size_row)

        # Text area size preset (tray height)
        layout.addWidget(QLabel("Text Area Size"))
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
            tray_row.addWidget(btn)
            self._tray_size_btns[sid] = btn
        self._tray_size_btns["medium"].setChecked(True)
        tray_row.addStretch()
        layout.addLayout(tray_row)

        # Advanced settings toggle (collapsible)
        layout.addWidget(self._divider())
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
        adv_panel_layout.addWidget(QLabel("Diff Threshold"))
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
        layout.addWidget(self._advanced_panel)
        self._advanced_panel.setVisible(False)

        self._advanced_toggle_btn.clicked.connect(
            lambda checked: self._set_advanced_visible(bool(checked))
        )
        self._set_advanced_visible(False)

        # Action buttons
        layout.addWidget(self._divider())
        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._reset_btn.setMinimumWidth(0)
        self._reset_btn.setMaximumWidth(16777215)
        self._reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(self._reset_btn)

        layout.addStretch()

        # Apply initial stylesheet
        self._apply_base_style()

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
        self.setStyleSheet(f"""
            #SideMenu {{
                background: {panel_bg};
                border-right: 1px solid {border};
            }}

            /* Scope all descendants to beat the global * rule */
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
                padding: 6px 12px;
                font-size: 13px;
                font-weight: 600;
            }}
            #SideMenu QPushButton[menuClass="option-btn"]:checked {{
                background: {accent};
                color: #ffffff;
                border-color: {accent};
            }}
            #SideMenu QPushButton[menuClass="option-btn"]:hover:!checked {{
                border-color: {btn_hover_border};
                background: {btn_hover_bg};
            }}

            #SideMenu QPushButton:not([menuClass]) {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {btn_border};
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            #SideMenu QPushButton:not([menuClass]):hover {{
                border-color: {accent};
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
            #SideMenu QScrollArea > QWidget > QWidget {{
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
        self._set_advanced_visible(False)
        self.reset_requested.emit()

    def _add_toggle_section(self, layout, title: str,
                           signal: pyqtSignal, default: bool):
        layout.addWidget(QLabel(title))
        row = QHBoxLayout()
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
        row.addWidget(on_btn)
        row.addWidget(off_btn)
        row.addStretch()
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

    def set_auto_read_selection(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._auto_read_toggle, enabled)
        if emit_signal:
            self.auto_read_selection_changed.emit(enabled)

    def set_auto_translate_selection(self, enabled: bool, *, emit_signal: bool = False) -> None:
        self._set_toggle_state(self._auto_translate_toggle, enabled)
        if emit_signal:
            self.auto_translate_selection_changed.emit(enabled)

    def _set_advanced_visible(self, visible: bool) -> None:
        if not hasattr(self, "_advanced_panel"):
            return
        self._advanced_toggle_btn.setChecked(visible)
        self._advanced_panel.setVisible(visible)

    def _on_translation_backend_clicked(self, backend_id: str) -> None:
        """Update backend button selection and show/hide URL field."""
        for bid, btn in self._backend_btns.items():
            btn.setChecked(bid == backend_id)
        # LibreTranslate is hidden for now, so URL field is always hidden
        url_visible = False
        self._libre_url_label.setVisible(url_visible)
        self._libre_url_edit.setVisible(url_visible)
        self.translation_backend_changed.emit(backend_id)

    def update_openai_usage(self, chars: int) -> None:
        self._openai_usage_label.setText(f"Session usage: {chars} chars")
