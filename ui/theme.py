"""Theme system — mirrors web app's CSS variable palettes."""

from dataclasses import dataclass


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
