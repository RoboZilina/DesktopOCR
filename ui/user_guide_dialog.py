from __future__ import annotations

import pathlib

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt


class UserGuideDialog(QDialog):
    def __init__(self, parent=None, guide_path: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("DesktopOCR User Guide")
        self.resize(720, 640)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        layout.addWidget(self._browser, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        guide_html = self._load_guide(guide_path)
        self._browser.setHtml(guide_html)

    def _load_guide(self, guide_path: str | None) -> str:
        if guide_path:
            path = pathlib.Path(guide_path)
        else:
            import sys
            _base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent.parent))
            path = _base / "docs" / "user_guide.html"

        if not path.exists():
            return ""  # silently ignore
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return """<h1>DesktopOCR User Guide</h1><p>Guide missing. Ensure docs/user_guide.html ships with the app.</p>"""
