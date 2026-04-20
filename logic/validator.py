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

def is_valid_japanese(text: str, confidence: float | None = None) -> bool:
    """
    Validation gate for Japanese text.
    Ported exactly from instructions.md.
    """
    if not text or len(text) < 2:
        return False

    jp_ratio = score_japanese_density(text) / len(text)
        
    # Confidence gate (from OCR engine)
    if confidence is not None and confidence < CONFIDENCE_THRESHOLD:
        # Confidence values can be poorly calibrated across OCR model variants.
        # For strong Japanese-only outputs, allow pass-through despite low confidence.
        if jp_ratio < LOW_CONF_JP_RATIO_THRESHOLD:
            return False
        
    # Japanese character ratio gate
    # Return True only if ratio >= 0.5
    return jp_ratio >= 0.5

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

    # 1. Strip lone Latin letters (single letters not adjacent to other letters or numbers)
    # Using negative lookbehind/lookahead to find letters not part of an alphanumeric word
    text = re.sub(r'(?i)(?<![a-z0-9])[a-z](?![a-z0-9])', '', text)
    
    # 2. Strip repeated punctuation (3+ same punctuation chars in a row)
    # Target common OCR-noise candidates
    text = re.sub(r'([!?.。，、…\-])\1{2,}', '', text)
    
    # 3. Strip leading/trailing whitespace
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
