"""Theme system — mirrors web app's CSS variable palettes."""

from dataclasses import dataclass
from pathlib import Path


def _scale_hex_color(color: str, factor: float) -> str:
    color = color.lstrip("#")
    if len(color) != 6:
        return f"#{color}"
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass(frozen=True)
class ThemePalette:
    bg: str
    panel: str
    accent: str
    accent_glow: str
    text: str
    text_dim: str
    text_secondary: str
    border: str
    panic: str
    warn: str
    name: str

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


DARK = ThemePalette(
    bg="#050506",
    panel="#0d0d10",
    accent="#10b981",
    accent_glow="rgba(16, 185, 129, 0.2)",
    text="#ffffff",
    text_dim="#a1a1aa",
    text_secondary="#8a8a93",
    border="#1f1f23",
    panic="#ef4444",
    warn="#f59e0b",
    name="dark",
)

LIGHT = ThemePalette(
    bg="#f8f9fa",
    panel="#ffffff",
    accent="#059669",
    accent_glow="rgba(5, 150, 105, 0.1)",
    text="#111827",
    text_dim="#4b5563",
    text_secondary="#6b7280",
    border="#e2e8f0",
    panic="#b91c1c",
    warn="#d97706",
    name="light",
)


def load_qss_template() -> str:
    template_path = Path(__file__).parent / "theme_template.qss"
    return template_path.read_text(encoding="utf-8")


def apply_theme(app, pal: ThemePalette):
    template = load_qss_template()
    hover = pal.accent_glow
    pressed = pal.accent
    accent_dark = _scale_hex_color(pal.accent, 0.85)
    disabled_bg = pal.border if pal.is_dark else "#e5e7eb"
    disabled_fg = pal.text_dim
    disabled_border = pal.border
    qss = (
        template
        .replace("{BG}", pal.bg)
        .replace("{PANEL}", pal.panel)
        .replace("{ACCENT}", pal.accent)
        .replace("{ACCENT_GLOW}", pal.accent_glow)
        .replace("{TEXT}", pal.text)
        .replace("{TEXT_DIM}", pal.text_dim)
        .replace("{TEXT_SECONDARY}", pal.text_secondary)
        .replace("{BORDER}", pal.border)
        .replace("{HOVER}", hover)
        .replace("{PRESSED}", pressed)
        .replace("{ACCENT_DARK}", accent_dark)
        .replace("{DISABLED_BG}", disabled_bg)
        .replace("{DISABLED_FG}", disabled_fg)
        .replace("{DISABLED_BORDER}", disabled_border)
    )
    app.setStyleSheet(qss)
