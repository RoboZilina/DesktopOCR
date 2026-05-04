# DesktopOCR
OCR for Japanese language content (Visual novels, Manga etc). 2026 Edition

## Version
DesktopOCR v1.0.0-rc3

## What's New in This Release
- Phase 5 documentation updates — improved user guide, port validation notes, PyInstaller bundling info
- Zero-risk code cleanup (unused imports removed, PEP8 formatting, invalid QSS removed, tooltips added, `.gitignore` expanded)
- Pre-release hardening prep (resource path fixes, settings type guards, packaging foundations)

> **Note:** EasyOCR is currently hidden from the engine selector and is not available in this release. Only PaddleOCR and Windows OCR are shown in the UI.

### Bundled Models

The offline ArgosTranslate JA→EN model (`assets/argos/ja_en.argosmodel`, ~111 MB) is excluded from Git due to GitHub's 100 MB file-size limit. It is bundled at build time via `build.ps1` (`--include-data-dir=assets=assets`).

Developers can obtain the model by running:
```bash
argospm install translate-ja_en
```
Or download it manually from the [Argos package index](https://github.com/argosopentech/argos-translate).

## Highlighting System

DesktopOCR includes an optional multi-layer highlighting system that helps you quickly identify word frequency and kanji difficulty while reading Japanese text.

### Dictionary Frequency (Underlines)

Words are underlined based on how common they are in everyday Japanese:

- **Solid underline** — very common word
- **Dotted underline** — less common word
- **Red wave underline** — rare word
- **No underline** — not in dictionary / unknown

Inflected forms (e.g., `行かない`, `読んでいた`) automatically inherit the rank of their base dictionary form.

### Kanji Category (Background Tint)

Individual kanji may receive a soft background tint:

- **Jōyō kanji** — standard everyday kanji
- **Jinmeiyō kanji** — name-use kanji

This layer is additive and does not overwrite dictionary underlines.

### Layer Interaction

Both passes can be enabled independently. When both are active:

- **Underlines** show word frequency
- **Background tints** show kanji category

These layers are independent and stack safely.

## Anki Integration

DesktopOCR can save OCR results (text, translation, screenshot, TTS audio) to [Anki](https://apps.ankiweb.net/) flashcards via the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on.

### Prerequisites

1. **Anki** installed and **running**
2. **AnkiConnect** add-on installed (Tools → Add-ons → Get Add-ons → code `2055492159`)

### Note Type

The app auto-creates a **DesktopOCR** note type with 7 fields:
- **Front** / **Back** — rendered HTML based on your template choices
- **TargetText** — the selected (or full OCR) text
- **TargetTranslation** — translation of the target text
- **ContextText** — full OCR output (surrounding context)
- **ContextTranslation** — translation of the context text
- **Screenshot** — full-window screenshot as an `<img>` tag

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Host | `localhost` | AnkiConnect host |
| Port | `8765` | AnkiConnect port |
| Deck | `DesktopOCR` | Target Anki deck (created automatically) |
| Tags | `japanese, vn` | Comma-separated tags on every card |
| Front Template | `screenshot` | Card front: screenshot, screenshot+text, or text-only |
| Back Template | `full_with_context` | Card back: full context, selection, or OCR-only |
| Audio Side | `front` | Attach TTS audio to front, back, or both |
| Auto-translate | `true` | Silently fetch a translation for the Anki card when saving (not used for in-app translation) |

### Quick Start

1. Open the side menu → **Anki Integration** section
2. Toggle **Enable Anki** on
3. Click **Test Connection** to verify AnkiConnect is reachable (the app also polls every 30s)
4. Get an OCR result, optionally select text and trigger translation
5. Click **🃏 Anki** to save a card to the `DesktopOCR` deck

> **Note:** Anki must be running for AnkiConnect to respond. The 🃏 button is always clickable when visible; if AnkiConnect is unreachable a dialog explains the issue.
>
> **Security note:** The AnkiConnect add-on (`2055492159`) is open-source. You can verify its code on [AnkiWeb](https://ankiweb.net/shared/info/2055492159) or review it locally in Anki's add-ons folder.

## Text-to-Speech

DesktopOCR supports multiple TTS backends. The voice selector in the top bar shows all currently available voices.

| Backend | Type | Requirements |
|---|---|---|
| **Edge TTS** | Cloud | Internet connection; no API key required |
| **OpenJTalk** | Local | Bundled; requires MeCab on PATH for most Windows setups |
| **COEIROINK** | Local | Download from [coeiroink.com](https://coeiroink.com/download); must be running at `127.0.0.1:50032` to appear in the voice selector |
| **VoiceVox** | Local | Stub — not yet implemented |

> **Note:** COEIROINK voices only appear when the COEIROINK server is running. Start it before launching DesktopOCR, or restart the app after starting the server.
