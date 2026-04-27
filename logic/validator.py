import re

# Japanese character ranges from instructions.md
JAPANESE_RANGES = [
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs (kanji)
    (0xFF65, 0xFF9F),  # Halfwidth Katakana
    (0x3400, 0x4DBF),  # CJK Extension A
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0xFF01, 0xFF60),  # Fullwidth symbols (！, ～, etc.)
    (0x2014, 0x2015),  # Em dash / horizontal bar (VN ellipsis chars)
    (0x2026, 0x2026),  # Horizontal ellipsis …
    (0x30FB, 0x30FB),  # Katakana middle dot ・
]

CONFIDENCE_THRESHOLD = 0.45
LOW_CONF_JP_RATIO_THRESHOLD = 0.8
ASCII_RATIO_HARD_REJECT = 0.70
ASCII_RATIO_SOFT_LIMIT = 0.25

UI_NOISE_TOKENS = {
    "save",
    "load",
    "system",
    "log",
    "skip",
    "auto",
    "config",
    "quicksave",
    "quickload",
    "voice",
    "repeat",
}


def _ascii_letter_ratio(text: str) -> float:
    if not text:
        return 0.0
    letters = sum(1 for c in text if "a" <= c.lower() <= "z")
    return letters / len(text)


def _contains_ui_noise_token(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(tok in lowered for tok in UI_NOISE_TOKENS)


def _is_symbol_heavy(text: str) -> bool:
    if not text:
        return True
    non_space = [c for c in text if not c.isspace()]
    if not non_space:
        return True
    symbol_count = sum(1 for c in non_space if not c.isalnum())
    return (symbol_count / len(non_space)) >= 0.85


def _has_kanji(text: str) -> bool:
    return any(0x4E00 <= ord(c) <= 0x9FFF for c in text)

def is_valid_japanese(text: str, confidence: float | None = None) -> bool:
    """
    Validation gate for Japanese text.
    Ported exactly from instructions.md.
    """
    if not text:
        return False

    text = text.strip()
    if len(text) < 2:
        return False

    if _contains_ui_noise_token(text):
        return False

    jp_count = score_japanese_density(text)
    jp_ratio = jp_count / len(text)
    ascii_ratio = _ascii_letter_ratio(text)

    if jp_count == 0:
        return False

    if _is_symbol_heavy(text) and jp_ratio < 0.5:
        return False

    if ascii_ratio >= ASCII_RATIO_HARD_REJECT and jp_ratio < 0.5:
        return False

    # Recall-first fast-path for strong Japanese fragments, even when confidence
    # is under-calibrated for noisy VN captures.
    if jp_ratio >= LOW_CONF_JP_RATIO_THRESHOLD and jp_count >= 2:
        return True

    # Hybrid-lite scoring for borderline lines.
    score = 0
    if jp_ratio >= 0.5:
        score += 2
    if jp_ratio >= 0.7:
        score += 1
    if _has_kanji(text):
        score += 1
    if len(text) >= 4:
        score += 1

    if ascii_ratio <= ASCII_RATIO_SOFT_LIMIT:
        score += 1
    elif ascii_ratio > 0.45:
        score -= 1

    if confidence is not None and confidence >= CONFIDENCE_THRESHOLD:
        score += 1

    return score >= 3

def score_japanese_density(text: str) -> float:
    """
    Count Japanese characters in text.
    Ported from capture_pipeline.js scoreJapaneseDensity logic.
    """
    if not text:
        return 0.0
        
    return sum(
        1 for c in text
        if any(lo <= ord(c) <= hi for lo, hi in JAPANESE_RANGES)
    )

def clean_ocr_output(text: str) -> str:
    """
    Clean OCR noise and artifacts.
    - Strip lone Latin letters mixed into Japanese
    - Strip repeated punctuation (3+)
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""

    # 1. Normalize whitespace early
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)

    # 2. Strip lone Latin letters (single letters not adjacent to other letters, numbers, or CJK)
    # Using negative lookbehind/lookahead and ensuring we don't remove characters glued to JP text
    text = re.sub(r'(?i)(?<![a-z0-9\u3040-\u9fff])[a-z](?![a-z0-9\u3040-\u9fff])', '', text)
    
    # 3. Strip repeated punctuation (3+ same punctuation chars in a row)
    # Target common OCR-noise candidates
    text = re.sub(r'([!?.。，、…\-])\1{2,}', '', text)

    # 4. Normalize common punctuation variants
    text = text.replace("，", "、").replace(",", "、")
    text = text.replace("．", "。").replace(".", "。")
    
    # 5. Strip leading/trailing whitespace
    return text.strip()

# ====================================================================
# PHASE 1: Enhanced Base Validator (8-Layer Pipeline)
# ====================================================================

# Layer 2 - UI artifact patterns
_UI_ARTIFACTS = re.compile(
    r'\[(?:[A-Za-z0-9\s%\.]+)\]'   # [NaN%], [object Object] etc.
    r'|\[undefined\]'
    r'|[\u2460-\u2473]'             # Circled digits ①②③
)

def _strip_ui_artifacts(text: str) -> str:
    return _UI_ARTIFACTS.sub('', text)

# Layer 3
def _strip_trailing_ascii_garbage(text: str) -> str:
    # Find last JP character position
    last_jp = -1
    for i, c in enumerate(text):
        if any(lo <= ord(c) <= hi for lo, hi in JAPANESE_RANGES):
            last_jp = i
    if last_jp == -1:
        return text  # no JP chars, return as-is
    # Keep up to and including last JP char, then allow only
    # JP punctuation after it — strip trailing ASCII symbols/letters
    tail = text[last_jp + 1:]
    # Allow: JP punctuation, spaces. Strip: ASCII letters, digits, symbols
    clean_tail = re.sub(r'[A-Za-z0-9!@#$%^&*\(\)\[\]{}<>|\\\/+=_~`]+', '', tail)
    return text[:last_jp + 1] + clean_tail

# Layer 4
PROTECTED_ACRONYMS = {
    'PC', 'TV', 'USB', 'GPU', 'CPU', 'VR', 'AR', 'AI', 
    'OK', 'NG', 'ID', 'HP', 'MP', 'BGM', 'SE', 'CG', 'OP', 'ED'
}

def _apply_smart_spacing(text: str) -> str:
    # 1. Remove accidental spaces INSIDE Japanese text
    text = re.sub(r'(?<=[\u3040-\u9FFF])\s+(?=[\u3040-\u9FFF])', '', text)
    # 2. Ensure exactly one space between Japanese and Latin blocks
    text = re.sub(r'(?<=[\u3040-\u9FFF])(?=[A-Za-z0-9])', ' ', text)
    text = re.sub(r'(?<=[A-Za-z0-9])(?=[\u3040-\u9FFF])', ' ', text)
    # 3. Collapse spaces inside protected acronyms
    for acr in PROTECTED_ACRONYMS:
        spaced_acr = ' '.join(acr)
        text = text.replace(spaced_acr, acr)
        # remove space before it to match JS logic
        text = re.sub(r'(?<=[\u3040-\u9FFF])\s+(?=' + acr + r'\b)', '', text)
    return text

# Layer 5
_VN_PROTECTED = [
    ('……', '\uE000'),
    ('――', '\uE001'),
    ('〜〜', '\uE002'),
    ('...', '\uE003'),
]

def _protect_vn_sequences(text: str) -> str:
    for original, placeholder in _VN_PROTECTED:
        text = text.replace(original, placeholder)
    return text

def _restore_vn_sequences(text: str) -> str:
    for original, placeholder in _VN_PROTECTED:
        text = text.replace(placeholder, original)
    return text

# Layer 6
def _normalize_punctuation(text: str) -> str:
    # Full-width comma ，→ 、
    text = text.replace('，', '、')
    # . between JP chars → 。
    text = re.sub(r'(?<=[\u3040-\u9FFF])\.(?=[\u3040-\u9FFF\s])', '。', text)
    # , between JP chars → 、
    text = re.sub(r'(?<=[\u3040-\u9FFF]),(?=[\u3040-\u9FFF\s])', '、', text)
    # Strip 3+ repeated punctuation
    text = re.sub(r'([!?.。，、…\-])\1{2,}', '', text)
    # Strip leading/trailing 「 」 if they are unmatched
    if text.startswith('「') and not text.endswith('」') and text.count('「') == 1 and text.count('」') == 0:
        text = text[1:]
    if text.endswith('」') and not text.startswith('「') and text.count('」') == 1 and text.count('「') == 0:
        text = text[:-1]
    return text

# Layer 7
_ASCII_FIXES = [
    (r'\b0\b', 'O'),        # standalone 0 → O
    (r'rn', 'm'),           # rn → m (very common OCR confusion)
    (r'(?<![A-Z])5(?![0-9])', 's'),  # 5 → s (not in numbers)
    (r'vv', 'w'),           # vv → w
    (r'l(?=[a-z])', 'I'),   # l followed by lowercase → I
]

def _fix_ascii_hallucinations(text: str) -> str:
    def replace_ascii_segment(match):
        seg = match.group(0)
        if seg.strip() in PROTECTED_ACRONYMS or len(seg.strip()) < 2:
            return seg
        for pattern, replacement in _ASCII_FIXES:
            seg = re.sub(pattern, replacement, seg)
        return seg
    return re.sub(r'[A-Za-z0-9\s!@#$%^&*()\[\]{}<>|\\/+=_~`.,:;?"\'-]+', replace_ascii_segment, text)

# Layer 8
def _final_normalize(text: str) -> str:
    # Normalize fullwidth space \u3000 → regular space
    text = text.replace('\u3000', ' ')
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Strip lone Latin letters unless they touch CJK characters
    text = re.sub(r'(?i)(?<![a-z0-9\u3040-\u9fff])[a-z](?![a-z0-9\u3040-\u9fff])', '', text)
    return text.strip()

def clean_ocr_output_enhanced(text: str) -> str:
    if not text:
        return ""
    text = _strip_ui_artifacts(text)          # Layer 2
    text = _protect_vn_sequences(text)        # Layer 5 pre-pass
    text = _strip_trailing_ascii_garbage(text) # Layer 3
    text = _apply_smart_spacing(text)         # Layer 4
    text = _normalize_punctuation(text)       # Layer 6
    text = _fix_ascii_hallucinations(text)    # Layer 7
    text = _restore_vn_sequences(text)        # Layer 5 post-pass
    text = _final_normalize(text)             # Layer 8
    return text


if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("こんにちは、世界！", 0.9, "Valid Japanese sentence"),
        ("lりAaん", 0.8, "Garbled OCR string"),
        ("", None, "Empty string"),
        ("This is English text", 0.95, "Pure English text"),
        ("あ..........", 0.8, "Japanese with noise punctuation"),
    ]
    
    print(f"{'Input':<25} | {'Valid?':<7} | {'Density':<7} | {'Cleaned'}")
    print("-" * 65)
    
    for text, conf, desc in test_cases:
        valid = is_valid_japanese(text, conf)
        density = score_japanese_density(text)
        cleaned = clean_ocr_output(text)
        print(f"{text:<25} | {str(valid):<7} | {density:<7.1f} | '{cleaned}'")
