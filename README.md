# DesktopOCR
OCR for Japanese language content (Visual novels, Manga etc). 2026 Edition

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

### Quick Start

1. Open the side menu → **Anki Integration** section
2. Toggle **Enable Anki** on
3. Click **Test Connection** to verify AnkiConnect is reachable (the app also polls every 30s)
4. Get an OCR result, optionally select text and trigger translation
5. Click **🃏 Anki** to save a card to the `DesktopOCR` deck

Default host: `localhost`, port: `8765`, deck: `DesktopOCR`.

> **Note:** Anki must be running for AnkiConnect to respond. The 🃏 button is always clickable when visible; if AnkiConnect is unreachable a dialog explains the issue.
