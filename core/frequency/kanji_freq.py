import logging
import os
from typing import Dict, Optional


logger = logging.getLogger(__name__)
_KANJI: Optional[Dict[str, int]] = None
_PATH = os.path.abspath(
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "resources", "kanji_freq.tsv")
    )
)


def load() -> Dict[str, int]:
    """Load kanji ranks from resources/kanji_freq.tsv; cache and return the dict."""
    global _KANJI
    if _KANJI is not None:
        return _KANJI

    freq: Dict[str, int] = {}
    try:
        with open(_PATH, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                parts = stripped.split("\t")
                if len(parts) < 2:
                    continue
                lemma = parts[0].strip()
                rank_str = parts[1].strip()
                if not lemma:
                    continue
                try:
                    rank = int(rank_str)
                except ValueError:
                    continue
                existing = freq.get(lemma)
                if existing is None or rank < existing:
                    freq[lemma] = rank
    except (OSError, UnicodeError) as exc:
        freq = {}
        logger.exception("Failed to load kanji frequency file %s", _PATH, exc_info=exc)

    _KANJI = freq
    logger.info("Kanji frequency table loaded: %d entries", len(_KANJI))
    return _KANJI


def lookup(word: str) -> Optional[int]:
    """Return the cached rank for the kanji if present; otherwise None."""
    if not word:
        return None
    freq = load()
    return freq.get(word)


def _self_test() -> None:
    freq = load()
    file_found = os.path.exists(_PATH)
    print(f"Kanji frequency file found: {file_found}")
    print(f"Kanji loaded: {len(freq)}")
    for char in ("日", "龍"):
        print(f"Lookup {char}: {freq.get(char)}")


if __name__ == "__main__":
    _self_test()
