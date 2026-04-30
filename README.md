# DesktopOCR
OCR for Japanese language content (Visual novels, Manga etc). 2026 Edition

## Highlighting System

DesktopOCR includes an optional multi-layer highlighting system that helps you quickly identify word frequency and kanji difficulty while reading Japanese text.

### Dictionary Frequency (Underlines)

Words are underlined based on how common they are in everyday Japanese:

- **Solid underline** — very common word
- **Dotted underline** — less common word
- **No underline** — rare or unknown word

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
