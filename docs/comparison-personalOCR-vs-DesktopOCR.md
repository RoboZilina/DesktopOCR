# DesktopOCR vs personalOCR-Cloudflare — Comparison

## Comparison Table

| Category | personalOCR-Cloudflare (v3.8.6) | DesktopOCR (v1.0.0-rc3) |
|---|---|---|
| **Platform** | Web Application (PWA), hosted on Cloudflare Pages | Native Windows desktop application (Python + PyQt6) |
| **OCR Engines** | Tesseract.js (browser WASM), PaddleOCR (ONNX Runtime Web via WebGPU), MangaOCR (Vision Transformer) | PaddleOCR (ONNX Runtime via DirectML GPU acceleration), Windows OCR (WinRT), Google Vision OCR (cloud fallback) |
| **Preprocessing Pipeline** | 8 image processing modes (Default Mini/Full, Adaptive, Multi-Pass, Contrast, Grayscale, Raw); Tesseract-only upscaling; PaddleOCR enforces raw input | VN-Stable Mode detection pipeline with configurable thresholds, adaptive box pruning, deduplication, trim padding with contrast boost, merge heuristics |
| **Speed & Latency** | Browser-bound; WebGPU requires COOP/COEP headers; Tesseract slower on large text; MangaOCR heavy (~1.2 GB VRAM) | Native DirectML GPU execution; optimized ONNX graph (~70% fewer nodes); significantly lower latency than browser WASM path |
| **Accuracy** | 3 quality tiers: Tesseract (good clean text), PaddleOCR (high Japanese), MangaOCR (highest manga, limited square crops) | PaddleOCR with VN-tuned thresholds, multi-line slicing, intelligent box merging; plus AI-assisted validation via DeepSeek/OpenAI |
| **Offline Capability** | Internet required for initial model download; Cloudflare needed for COOP/COEP; browser must remain open | Partially offline — OCR and local TTS (OpenJTalk) work without internet; translation (MyMemory/Google) and AI validation require cloud APIs |
| **Model Size / Performance** | PaddleOCR models hosted remotely (Cloudflare R2); MangaOCR ~450 MB download; Tesseract WASM ~12 MB | PaddleOCR models ~166 MB total bundled locally; graph-optimized for DirectML; FP32 (no quantization) |
| **UI Responsiveness** | Web-based DOM rendering; status pill with progress tracking; browser event loop jank possible | Native PyQt6 desktop UI; dedicated event loop; auto-clearing status bar; always-on-top; no GC pauses |
| **Hotkeys & Capture** | Browser Screen Capture API requires user gesture; no system-wide hotkeys; auto-capture via video frame polling | System-wide global hotkey (configurable); WinRT Graphics Capture; auto-capture with stabilization delay and frame diff detection |
| **Validators & Post-Processing** | 8-layer deterministic VN text cleaner (character protection, garbage removal, punctuation normalization, spacing rules, English OCR fixes, VN-specific rules, heuristic safety, final trim) | Deterministic validator (same 8-layer approach) PLUS DeepSeek AI validator and OpenAI validator; noise token filtering, Japanese density scoring, confidence gating |
| **Translation & TTS** | Browser Web Speech API (limited system voices; no Japanese-specific engines); no translation | Multi-backend TTS: Edge TTS (cloud), OpenJTalk (local), COEIROINK (local, requires server); translation via MyMemory (free web API, no key required, needs internet) or Google Translate (needs internet); LibreTranslate (local, not yet bundled) |
| **Anki Integration** | None | Full AnkiConnect integration — flashcards with OCR text, readings, translation, audio; configurable templates |
| **Frequency / Highlighting** | None | Word frequency analysis (jp_freq.tsv) and kanji difficulty annotation (kanji_freq.tsv); visual underlines + background tints |
| **Privacy** | Runs in browser; no server processing; Cloudflare sees IP on model downloads | Fully local; no telemetry; cloud APIs (DeepSeek, OpenAI, Google Vision, Edge TTS) are optional and user-toggled; screenshots never leave machine |
| **Deployment** | Deployed to Cloudflare Pages; URL accessible from any device; no installation | Windows app (pip install or PyInstaller EXE); requires Python 3.11+ and Windows 10/11 |
| **Web Version Limitations** | Requires Chromium with WebGPU; COOP/COEP needed for multi-threading; no system-wide captures; no offline TTS; no Anki; no global hotkeys; browser must stay active | Windows-only; ~166 MB download; Python setup needed (unless using EXE); DirectML requires compatible GPU or falls back to CPU |

---

## Which One Should You Choose?

### Choose personalOCR-Cloudflare if:

- You need a lightweight, **zero-install** OCR solution that runs in any modern browser
- You read manga and need **MangaOCR** for comic panels
- You prefer **Tesseract** for simple, clean text extraction
- You're comfortable with **Cloudflare Pages** hosting and managing your own deployment
- You only need **basic text-to-speech** via browser APIs
- You work across multiple devices and want a URL-based solution

### Choose DesktopOCR if:

- You need the **fastest, most responsive** OCR experience on Windows with **native DirectML GPU acceleration**
- You want **offline OCR and TTS** — models bundled locally; translation (MyMemory/Google) and AI validation still need internet
- You need **Anki integration** to create flashcards directly from captured text
- You want **AI-assisted validation** via DeepSeek or OpenAI, and **translation** via MyMemory or Google Translate
- You need **word frequency and kanji highlighting** for Japanese reading support
- You require **system-wide hotkeys** and desktop-level screen capture
- You prefer **multiple TTS options** including local Japanese voice engines (OpenJTalk, COEIROINK)
- Privacy matters — all processing stays on your machine

### Verdict

personalOCR-Cloudflare is a capable browser-based tool perfect for casual use, manga reading, and multi-device setups. DesktopOCR is the heavyweight desktop companion — it trades portability for power, offering native performance, offline resilience, a rich toolset (Anki, AI validators, frequency analysis, multi-backend TTS), and deep desktop integration that a browser simply cannot match.
