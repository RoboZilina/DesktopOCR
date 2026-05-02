"""Build and send Anki cards from OCR results."""

from __future__ import annotations

import asyncio
import base64
import html
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
    audio_paths: list[str] | None,
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
        audio_paths: List of paths to TTS audio files to attach, or ``None``.
            When multiple paths are provided (e.g. target + context audio),
            each gets a unique filename and is embedded in the card.
        config: Settings dict containing ``anki_*`` keys (see module docstring).

    Returns:
        ``True`` if the card was saved successfully, ``False`` otherwise.
    """
    # ------------------------------------------------------------------
    # 1. Grab screenshot from the last preview frame
    # ------------------------------------------------------------------
    screenshot_b64: str | None = None
    try:
        full_frame = capture.last_frame
        logger.info(
            "[Anki] Screenshot: capture.last_frame is %s (type=%s)",
            "None" if full_frame is None else f"ndarray shape={full_frame.shape}",
            type(full_frame).__name__ if full_frame is not None else "N/A",
        )
        if full_frame is not None:
            success, buf = cv2.imencode(".png", full_frame)
            if success:
                # buf is a numpy ndarray; convert to bytes before base64
                screenshot_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            else:
                logger.warning("[Anki] Screenshot: cv2.imencode failed on last_frame")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Anki] Screenshot exception: %s", exc)
    if screenshot_b64 is None:
        logger.warning("[Anki] No preview frame available for screenshot, continuing without it")

    # ------------------------------------------------------------------
    # 2. Determine target text
    # ------------------------------------------------------------------
    target_text = (selection_text or "").strip() or (ocr_text or "").strip()
    logger.info(
        "[Anki] target_text computed: target_text='%s' (selection=%r, ocr=%r, selection_empty=%r, ocr_empty=%r)",
        target_text[:60] if target_text else "(empty)",
        bool(selection_text),
        bool(ocr_text),
        not (selection_text or "").strip(),
        not (ocr_text or "").strip(),
    )

    # Empty-text guard — reject card creation when there is nothing to study.
    if not target_text:
        logger.warning("[Anki] No target text available, skipping card creation")
        anki._set_error("No target text to save")
        return False

    # ------------------------------------------------------------------
    # 3. Build fields dict
    # ------------------------------------------------------------------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    screenshot_filename = f"desktopocr_{timestamp}.png"

    fields: dict[str, str] = {
        "TargetText": target_text,
        "TargetTranslation": (selection_translation or "").strip(),
        "ContextText": (ocr_text or "").strip(),
        "ContextTranslation": (ocr_translation or "").strip(),
        "Screenshot": (
            f'<img src="{screenshot_filename}">' if screenshot_b64 else ""
        ),
    }
    logger.info(
        "[Anki] fields dict built: TargetText='%s' (len=%d), ContextText='%s' (len=%d), "
        "TargetTranslation='%s' (len=%d), ContextTranslation='%s' (len=%d), has_screenshot=%r",
        fields["TargetText"][:60] if fields["TargetText"] else "(empty)",
        len(fields["TargetText"]),
        fields["ContextText"][:60] if fields["ContextText"] else "(empty)",
        len(fields["ContextText"]),
        fields["TargetTranslation"][:60] if fields["TargetTranslation"] else "(empty)",
        len(fields["TargetTranslation"]),
        fields["ContextTranslation"][:60] if fields["ContextTranslation"] else "(empty)",
        len(fields["ContextTranslation"]),
        bool(screenshot_b64),
    )

    # ------------------------------------------------------------------
    # 4. Build front HTML
    # ------------------------------------------------------------------
    front_mode = config.get("anki_front", "screenshot")

    # When screenshot is unavailable, fall back to text-only front templates
    # so the card is still usable for study.
    # Use ContextText as the fallback content so the front is never blank
    # when there is no selection text.
    if not screenshot_b64 and front_mode in ("screenshot", "screenshot_selection"):
        logger.info("[Anki] Screenshot unavailable, falling back to text-only front (context=%s)", bool(target_text))
        if target_text:
            front_html = "<div class='target'>{TargetText}</div>"
        else:
            front_html = "<div class='context'>{ContextText}</div>"
    elif front_mode == "screenshot":
        front_html = "{Screenshot}"
    elif front_mode == "screenshot_selection":
        front_html = "{Screenshot}<br><div class='target'>{TargetText}</div>"
    elif front_mode == "selection_only":
        front_html = "<div class='target'>{TargetText}</div>"
    else:
        logger.warning("[Anki] Unknown front_mode '%s', falling back to screenshot", front_mode)
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
        front_html = front_html.replace(placeholder, html.escape(value))
        back_html = back_html.replace(placeholder, html.escape(value))

    logger.info(
        "[Anki] After substitution: front_html (first 150 chars)='%s', front_html_is_empty=%r",
        front_html[:150].replace("\n", "\\n"),
        not front_html.strip() or front_html.strip() in ("", "<div class='target'></div>", "<div class='context'></div>"),
    )

    fields["Front"] = front_html
    fields["Back"] = back_html

    logger.info(
        "[Anki] Final fields: Front='%s' (len=%d), Back='%s' (len=%d)",
        fields["Front"][:80] if fields["Front"] else "(empty)",
        len(fields["Front"]),
        fields["Back"][:80] if fields["Back"] else "(empty)",
        len(fields["Back"]),
    )

    # ------------------------------------------------------------------
    # 6. Build audio dicts for all available audio files
    # ------------------------------------------------------------------
    # Build audio dicts for all available audio files.
    # The caller provides both target and context audio when
    # full_with_context is enabled; AnkiConnect accepts an array.
    audio_dicts: list[dict[str, Any]] = []
    audio_paths = audio_paths or []
    audio_side = config.get("anki_audio_side", "front")
    if audio_side == "front":
        audio_fields = ["Front"]
    elif audio_side == "back":
        audio_fields = ["Back"]
    else:  # "both"
        audio_fields = ["Front", "Back"]

    for idx, path in enumerate(audio_paths):
        if path and os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    audio_b64 = base64.b64encode(f.read()).decode("ascii")
                filename = f"desktopocr_audio_{timestamp}_{idx}.mp3"
                # Target audio (idx=0) follows user's audio_side setting
                # (front, back, or both configurable in side menu).
                # Context audio (idx>=1, e.g. full_with_context) always attaches to Back only,
                # since ContextText/ContextTranslation render on the back of the card.
                fields_for_this = audio_fields if idx == 0 else ["Back"]
                audio_dicts.append({
                    "data": audio_b64,
                    "filename": filename,
                    "fields": fields_for_this,
                })
            except Exception:  # noqa: BLE001
                logger.warning("[Anki] Failed to read audio file %s", path)

    # ------------------------------------------------------------------
    # 7. Build picture dict for screenshot
    # ------------------------------------------------------------------
    picture_dict: dict | None = None
    if screenshot_b64:
        # Picture dict stores the image in Anki's media collection.
        # The <img> tags are already embedded in the Front/Back fields
        # via {Screenshot} substitution above; keep fields empty to
        # avoid duplicate <img> insertion by AnkiConnect.
        picture_dict = {
            "data": screenshot_b64,
            "filename": screenshot_filename,
            "fields": [],
        }

    # ------------------------------------------------------------------
    # 8. Parse tags
    # ------------------------------------------------------------------
    tags_str = config.get("anki_tags", "japanese, vn")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    # ------------------------------------------------------------------
    # 9. Send to Anki
    # ------------------------------------------------------------------
    deck_name = config.get("anki_deck", "DesktopOCR")

    try:
        if not await anki.ensure_deck(deck_name):
            logger.warning("[Anki] Failed to ensure deck '%s'", deck_name)
            return False

        if not await anki.ensure_note_type():
            logger.warning("[Anki] Failed to ensure note type 'DesktopOCR'")
            return False

        note_id = await anki.add_note(
            deck_name,
            fields,
            tags,
            audio=audio_dicts if audio_dicts else None,
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
        logger.warning("[Anki] Card not saved (duplicate detected or add_note returned None)")
        return False
    except Exception:  # noqa: BLE001
        logger.warning("[Anki] Card save raised unexpectedly", exc_info=True)
        return False
