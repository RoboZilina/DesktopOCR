import logging
import os
from typing import Dict, Optional


logger = logging.getLogger(__name__)
_FREQ: Optional[Dict[str, int]] = None
_PATH = os.path.abspath(
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "resources", "jp_freq.tsv")
    )
)


def load() -> Dict[str, int]:
    """Load lemma ranks from resources/jp_freq.tsv; cache and return the dict."""
    global _FREQ
    if _FREQ is not None:
        return _FREQ

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
        logger.exception("Failed to load frequency file %s", _PATH, exc_info=exc)

    _FREQ = freq
    logger.info("Frequency table loaded: %d entries", len(_FREQ))
    return _FREQ


def lookup(word: str) -> Optional[int]:
    """Return the cached rank for the word if present; otherwise None."""
    if not word:
        return None
    freq = load()
    return freq.get(word)


def _self_test() -> None:
    freq = load()
    file_found = os.path.exists(_PATH)
    print(f"Frequency file found: {file_found}")
    print(f"Lemmas loaded: {len(freq)}")
    for lemma in ("する", "存在"):
        print(f"Lookup {lemma}: {freq.get(lemma)}")


if __name__ == "__main__":
    _self_test()
