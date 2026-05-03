"""Argos Translate offline backend — JA→EN only, silent fallback.

Used as the last resort when all cloud translators fail or when
the user has no internet connection. The JA→EN model is bundled
with DesktopOCR under ``assets/argos/ja_en.argosmodel`` — no network
access is performed at runtime.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import argostranslate.package
import argostranslate.translate

from core.translation.base import TranslationBackend

logger = logging.getLogger(__name__)


class ArgosTranslatorBackend(TranslationBackend):
    """Offline JA→EN translation via Argos Translate.

    Installs the JA→EN model from the bundled file
    ``assets/argos/ja_en.argosmodel`` on first use.
    Only supports Japanese → English.  Returns empty string for all
    other pairs.
    """

    name: str = "ArgosTranslate"

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._installed = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bundled_model_path() -> str:
        """Return the absolute path to the bundled JA→EN model file.

        Resolved relative to this source file in development, or relative
        to the executable / bundle root in Nuitka / PyInstaller frozen builds.
        """
        if getattr(sys, "frozen", False):
            # PyInstaller: files are bundled under sys._MEIPASS
            if hasattr(sys, "_MEIPASS"):
                base = sys._MEIPASS
            # Nuitka standalone: files sit next to the executable
            else:
                base = os.path.dirname(sys.executable)
        else:
            # Development: __file__ is reliable
            base = Path(__file__).resolve().parent.parent.parent
        return os.path.join(str(base), "assets", "argos", "ja_en.argosmodel")

    @staticmethod
    def _bundled_model_exists() -> bool:
        """Cheap predicate — does the bundled model file exist on disk?

        Does NOT trigger model installation.  Safe to call from the
        event loop without an executor.
        """
        return os.path.isfile(ArgosTranslatorBackend._bundled_model_path())

    def _ensure_model_sync(self) -> bool:
        """Synchronous model installation (runs in executor thread).

        Returns ``True`` if the model is ready, ``False`` otherwise.
        Not reentrant — callers must serialise via ``self._lock``.
        """
        if self._installed:
            return True

        try:
            # --- Already installed in the argos package cache? ----------
            installed = argostranslate.translate.get_installed_languages()
            for lang in installed:
                if lang.code == "ja":
                    for t in lang.translations_to:
                        if t.to_lang.code == "en":
                            self._installed = True
                            return True

            # --- Install from bundled file -------------------------------
            model_path = self._bundled_model_path()
            if not os.path.isfile(model_path):
                return False

            argostranslate.package.install_from_path(model_path)
            self._installed = True
            return True

        except Exception:  # noqa: BLE001 — silent by design
            return False

    async def _ensure_model(self) -> bool:
        """Ensure the JA→EN model is installed (thread-safe, async).

        Uses double-checked locking:
        1. Fast-path check (no lock) — most calls after first use.
        2. Lock acquisition.
        3. Second check (after lock) — handles concurrent arrival.
        4. Blocking install offloaded to a thread-pool executor.
        """
        if self._installed:
            return True
        async with self._lock:
            if self._installed:
                return True
            return await asyncio.to_thread(self._ensure_model_sync)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def translate(
        self,
        text: str,
        source: str = "ja",
        target: str = "en",
    ) -> str:
        """Translate JA→EN via Argos Translate.

        Returns empty string on any failure or unsupported language pair.
        Blocking model installation and neural inference are offloaded
        to a thread-pool executor so the event loop stays responsive.
        """
        if not text or not text.strip():
            return ""
        if source != "ja" or target != "en":
            return ""
        if not self._installed and not await self._ensure_model():
            return ""
        try:
            result = await asyncio.to_thread(
                argostranslate.translate.translate,
                text,
                "ja",
                "en",
            )
            return result or ""
        except Exception:  # noqa: BLE001
            logger.warning(
                "[Argos] translate(%r) failed", text[:40], exc_info=True
            )
            return ""

    async def is_available(self) -> bool:
        """Return ``True`` if the bundled model file exists on disk.

        This is a cheap file-exists check — does NOT trigger model
        installation or package scan.  Use :meth:`translate` to
        actually install and use the model.
        """
        return self._bundled_model_exists()

    async def dispose(self) -> None:
        """No-op — Argos has no disposable session or network handles."""
