"""Build and send Anki cards from OCR results."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from datetime import datetime
from typing import Any

import cv2
import numpy as np

from core.capture import ScreenCapture
from logic.anki_connect import AnkiConnect

logger = logging.getLogger(__name__)


async def build_and_send_card(
    anki: AnkiConnect,
    capture: ScreenCapture,
    ocr_text: str,
    selection_text: str | None,
    ocr_translation: str | None,
    selection_translation: str | None,
    audio_path: str | None,
    config: dict,
) -> bool:
    """Capture a full-window screenshot, assemble an Anki note, and send it.

    Args:
        anki: Initialised :class:`AnkiConnect` client.
        capture: :class:`ScreenCapture` instance used to grab the screenshot.
        ocr_text: Full OCR output text.
        selection_text: User-selected text (subset of OCR output), or ``None``.
        ocr_translation: Translation of the full OCR text, or ``None``.
        selection_translation: Translation of the selection text, or ``None``.
        audio_path: Path to a TTS audio file to attach, or ``None``.
        config: Settings dict containing ``anki_*`` keys (see module docstring).

    Returns:
        ``True`` if the card was saved successfully, ``False`` otherwise.
    """
    # ------------------------------------------------------------------
    # 1. Grab full-window screenshot
    # ------------------------------------------------------------------
    screenshot_b64: str | None = None
    try:
        full_frame = await capture.get_frame(full=True)
        if full_frame is not None:
            success, buf = cv2.imencode(".png", full_frame)
            if success:
                screenshot_b64 = base64.b64encode(buf).tobytes().decode("ascii")
    except Exception:  # noqa: BLE001
        logger.warning("[Anki] Screenshot capture failed, continuing without it")

    # ------------------------------------------------------------------
    # 2. Determine target text
    # ------------------------------------------------------------------
    target_text = (selection_text or "").strip() or (ocr_text or "").strip()

    # ------------------------------------------------------------------
    # 3. Build fields dict
    # ------------------------------------------------------------------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_filename = f"desktopocr_{timestamp}.png"

    fields: dict[str, str] = {
        "TargetText": (selection_text or "").strip(),
        "TargetTranslation": (selection_translation or "").strip(),
        "ContextText": (ocr_text or "").strip(),
        "ContextTranslation": (ocr_translation or "").strip(),
        "Screenshot": (
            f'<img src="{screenshot_filename}">' if screenshot_b64 else ""
        ),
    }

    # ------------------------------------------------------------------
    # 4. Build front HTML
    # ------------------------------------------------------------------
    front_mode = config.get("anki_front", "screenshot")
    if front_mode == "screenshot":
        front_html = "{Screenshot}"
    elif front_mode == "screenshot_selection":
        front_html = "{Screenshot}<br><div class='target'>{TargetText}</div>"
    elif front_mode == "selection_only":
        front_html = "<div class='target'>{TargetText}</div>"
    else:
        front_html = "{Screenshot}"

    # ------------------------------------------------------------------
    # 5. Build back HTML
    # ------------------------------------------------------------------
    back_mode = config.get("anki_back", "full_with_context")
    if back_mode == "full_with_context":
        back_html = (
            "<div class='target'>{TargetText}</div>"
            "<div class='translation'>{TargetTranslation}</div>"
            "<hr>"
            "<div class='context'>{ContextText}</div>"
            "<div class='context-translation'>{ContextTranslation}</div>"
        )
    elif back_mode == "selection_only":
        back_html = (
            "<div class='target'>{TargetText}</div>"
            "<div class='translation'>{TargetTranslation}</div>"
        )
    elif back_mode == "full_only":
        back_html = (
            "<div class='context'>{ContextText}</div>"
            "<div class='translation'>{ContextTranslation}</div>"
        )
    else:
        back_html = (
            "<div class='target'>{TargetText}</div>"
            "<div class='translation'>{TargetTranslation}</div>"
            "<hr>"
            "<div class='context'>{ContextText}</div>"
            "<div class='context-translation'>{ContextTranslation}</div>"
        )

    # Substitute field values into HTML before assigning to Front/Back.
    # Anki's card template uses {{FieldName}} syntax in the template itself,
    # but the field values must contain the actual rendered HTML content.
    _subs = {
        "{Screenshot}": fields.get("Screenshot", ""),
        "{TargetText}": fields.get("TargetText", ""),
        "{TargetTranslation}": fields.get("TargetTranslation", ""),
        "{ContextText}": fields.get("ContextText", ""),
        "{ContextTranslation}": fields.get("ContextTranslation", ""),
    }
    for placeholder, value in _subs.items():
        front_html = front_html.replace(placeholder, value)
        back_html = back_html.replace(placeholder, value)

    fields["Front"] = front_html
    fields["Back"] = back_html

    # ------------------------------------------------------------------
    # 6. Build audio dict
    # ------------------------------------------------------------------
    audio_dict: dict | None = None
    if audio_path and os.path.isfile(audio_path):
        try:
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("ascii")
            audio_side = config.get("anki_audio_side", "front")
            if audio_side == "front":
                audio_fields = ["Front"]
            elif audio_side == "back":
                audio_fields = ["Back"]
            else:  # "both"
                audio_fields = ["Front", "Back"]
            audio_dict = {
                "data": audio_b64,
                "filename": "desktopocr_audio.mp3",
                "fields": audio_fields,
            }
        except Exception:  # noqa: BLE001
            logger.warning("[Anki] Failed to read audio file %s", audio_path)

    # ------------------------------------------------------------------
    # 7. Build picture dict for screenshot
    # ------------------------------------------------------------------
    picture_dict: dict | None = None
    if screenshot_b64:
        picture_dict = {
            "data": screenshot_b64,
            "filename": screenshot_filename,
            "fields": ["Front", "Back"],
        }

    # ------------------------------------------------------------------
    # 8. Parse tags
    # ------------------------------------------------------------------
    tags_str = config.get("anki_tags", "japanese vn")
    tags = [t.strip() for t in tags_str.split() if t.strip()]

    # ------------------------------------------------------------------
    # 9. Send to Anki
    # ------------------------------------------------------------------
    deck_name = config.get("anki_deck", "DesktopOCR")

    try:
        if not await anki.ensure_deck(deck_name):
            logger.warning("[Anki] Failed to ensure deck '%s'", deck_name)
            return False

        note_id = await anki.add_note(
            deck_name,
            fields,
            tags,
            audio=audio_dict,
            picture=picture_dict,
        )
        if note_id is not None:
            logger.info(
                "[Anki] Card saved | target='%s' | deck=%s | id=%d",
                target_text[:30],
                deck_name,
                note_id,
            )
            return True
        logger.warning("[Anki] Card save failed")
        return False
    except Exception:  # noqa: BLE001
        logger.warning("[Anki] Card save raised unexpectedly", exc_info=True)
        return False
