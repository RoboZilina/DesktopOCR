# DesktopOCR v1.0.0-rc4 — Release Notes

## New in This Release

### Anki Audio Positioning Redesign
- **Removed `anki_audio_side` setting** — audio placement is now derived automatically from your front/back card templates rather than requiring a separate configuration option
- **Template-derived audio injection**: TTS audio for the target text (`{TargetText}`) is placed next to `{TargetText}` in the template where it appears; context audio (`{ContextText}`) is placed next to `{ContextText}` in the back template. If a placeholder is absent from a template, the corresponding audio is inserted at the beginning of `back_html`
- **Fixed audio duplication bug**: Previously, setting `anki_audio_side: "both"` would attach `[sound:]` to both Front and Back fields via AnkiConnect's auto-attach, causing double playback on the back side (because `{{FrontSide}}` replays front content). Now audio files are uploaded with `fields: []` (media collection only) and `[sound:]` tags are injected manually into the HTML at precise positions
- **Fixed missing front audio**: With the `screenshot` front template (no `{TargetText}`), audio is placed at the beginning of the back HTML — audible on card flip without text anchoring issues
- **Fix applied to all 9 template combinations**: Front (`screenshot`, `screenshot_selection`, `selection_only`) × Back (`full_with_context`, `selection_only`, `full_only`)

### QComboBox Wheel Scroll Suppression
- Mouse wheel scrolling over dropdown menus no longer accidentally changes the selection. This affects all 6 combo boxes: engine selector, voice selector, OpenAI/DeepSeek model selectors, and Anki front/back template selectors

### Code Quality
- Removed 3 unused imports (`asyncio`, `time`, `numpy`) from `anki_card_builder.py`
- Renumbered duplicate section labels in `anki_card_builder.py`
- Cleaned up extra blank lines in `main.py`
- Updated help HTML to describe template-derived audio behavior

## Files Changed

| File | Change |
|------|--------|
| `main.py` | Version bump; removed `anki_audio_side` from defaults, validation, UI wiring, and signal handler |
| `logic/anki_card_builder.py` | Template-derived audio injection (before placeholder substitution); removed unused imports |
| `ui/side_menu.py` | Removed Audio Side combo widget and signal; added wheelEvent suppression to 4 combos; updated help HTML |
| `ui/controls_bar.py` | Added wheelEvent suppression to engine and voice combos |
| `settings.json` | Removed `anki_audio_side` key |
| `settings.json.example` | Removed `anki_audio_side` key |
| `docs/release-notes-v1.0.0-rc4.md` | This file |

## Upgrade Notes

- **Existing `settings.json` files** with `anki_audio_side` will load without error (the key is ignored if present). No manual migration needed
- **Audio behavior** after upgrade: TTS audio is placed automatically based on which templates contain `{TargetText}` and `{ContextText}`. If you previously relied on `anki_audio_side: "both"` for a specific workflow, verify the audio positions are correct for your template setup
