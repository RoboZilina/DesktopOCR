import re

# Japanese character ranges from instructions.md
JAPANESE_RANGES = [
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs (kanji)
    (0xFF65, 0xFF9F),  # Halfwidth Katakana
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

    # 2. Strip lone Latin letters (single letters not adjacent to other letters or numbers)
    # Using negative lookbehind/lookahead to find letters not part of an alphanumeric word
    text = re.sub(r'(?i)(?<![a-z0-9])[a-z](?![a-z0-9])', '', text)
    
    # 3. Strip repeated punctuation (3+ same punctuation chars in a row)
    # Target common OCR-noise candidates
    text = re.sub(r'([!?.。，、…\-])\1{2,}', '', text)

    # 4. Normalize common punctuation variants
    text = text.replace("，", "、").replace(",", "、")
    text = text.replace("．", "。").replace(".", "。")
    
    # 5. Strip leading/trailing whitespace
    return text.strip()

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
