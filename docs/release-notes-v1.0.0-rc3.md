# DesktopOCR v1.0.0-rc3 — Release Notes

## What DesktopOCR Adds on Top of personalOCR-Cloudflare

DesktopOCR evolved from the personalOCR-Cloudflare codebase as a ground-up native Windows adaptation. While personalOCR-Cloudflare is a browser-based PWA, DesktopOCR rewrites the stack in Python with PyQt6, DirectML, and WinRT APIs to deliver a true desktop experience. Every component — from screen capture to TTS — has been re-architected for native performance.

## New Features

- **Native Windows Screen Capture** — WinRT Windows.Graphics.Capture API for low-level, high-performance frame grabbing; supports any window or region without browser restrictions
- **DirectML GPU Acceleration** — PaddleOCR runs via onnxruntime-directml on compatible GPUs; graph-optimized models with ~70% fewer nodes for lower latency
- **Anki Integration** — One-click flashcard creation from captured text via AnkiConnect; configurable templates with readings and translation
- **Word Frequency & Kanji Analysis** — Built-in frequency tables annotate OCR results with word rarity underlines and kanji difficulty background tints
- **AI-Powered Validation** — DeepSeek and OpenAI validators for on-demand OCR text correction
- **Multi-Backend Translation** — MyMemory (free web API, no API key, needs internet) and Google Translate (needs internet) for Japanese-to-English translation; ArgosTranslate (offline, bundled with app)
- **Multi-Backend Text-to-Speech** — Edge TTS (cloud, natural voices), OpenJTalk (local), COEIROINK (local, requires server); runtime backend switching
- **Windows OCR Fallback** — Built-in Windows.Media.Ocr for Japanese text recognition without external models
- **Google Vision OCR Cloud Fallback** — Optional cloud-based OCR when local models struggle
- **System-Wide Global Hotkey** — Configurable hotkey to trigger OCR from any application
- **PyInstaller Packaging** — Standalone `.exe` build for distribution without Python dependencies

## Improvements

- **VN-Stable Detection Mode** — Production-hardened detection thresholds tuned for visual novel text boxes
- **Optimized ONNX Models** — Graph-optimized before bundling: det 1,045 to 266 nodes (-74.5%), rec 903 to 278 nodes (-69.2%)
- **Deterministic Text Validation** — Enhanced 8-layer Japanese text cleaner with additional noise token filtering
- **Async-First Architecture** — Fully async OCR pipeline (qasync + asyncio) prevents UI freezing during inference
- **Graceful Engine Fallback** — PaddleOCR loading issues auto-recover; Windows OCR serves as built-in fallback

## Bug Fixes

- Persistent WinRT capture session (no per-capture user gesture required)
- No browser memory pressure or GC stalls during extended sessions
- Fixed model loading race conditions with async locks and generation counters
- Fixed detection box deduplication edge cases with overlapping regions
- Fixed TTS backend switching not persisting across sessions
- Fixed AnkiConnect timeout handling for slow Anki responses
- Resource path resolution for PyInstaller bundled builds
- Settings type validation to prevent crashes from malformed config

## Performance Gains

- **OCR Latency**: ~40-60% reduction vs browser WebGPU path due to native DirectML and graph-optimized models
- **Frame Capture**: WinRT Graphics Capture delivers consistent ~16ms frame grabs
- **Memory**: No browser heap pressure; deterministic allocation; pre-allocated tensor buffers
- **Startup**: Models loaded once, sessions persist; no per-request model fetch from CDN

## Stability Improvements

- Graceful DirectML-to-CPU fallback
- Per-engine processing locks prevent concurrent inference corruption
- Generation counting discards stale results
- Failed engine loads auto-retry; corrupted sessions re-created
- Comprehensive structured logging with rotation
- All async operations have timeout guards; network calls wrapped in try/except

## Known Limitations

- **Windows Only**: Requires Windows 10/11 (21H2+). No macOS or Linux support
- **Python Required for Dev**: Python 3.11+ with pip; pre-built EXE available for end users
- **GPU Dependency**: DirectML requires DirectX 12 compatible GPU; falls back to CPU
- **No MangaOCR**: MangaOCR not ported — DesktopOCR focuses on horizontal game text
- **No Tesseract**: Only PaddleOCR and Windows OCR available
- **Model Size**: ~166 MB bundled PaddleOCR models (FP32); no quantization applied
- **Local TTS Setup**: COEIROINK requires a separate local HTTP server (127.0.0.1:50032). Download from [coeiroink.com/download](https://coeiroink.com/download) and start the server before launching DesktopOCR — voices only appear in the selector while the server is running. VoiceVox is a stub and not yet implemented
- **Offline Translation**: ArgosTranslate serves as offline fallback when no internet is available. The JA→EN model (~111 MB) is bundled into pre-built EXEs. Developers running from source must install the model separately via `argospm install translate-ja_en`. Cloud APIs (MyMemory, Google) are tried first
- **API Keys Required**: DeepSeek, OpenAI, Google Vision, and Edge TTS need user-provided keys or internet
