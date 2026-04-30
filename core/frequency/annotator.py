from __future__ import annotations

import logging
import os
import sys
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional

if __package__ in (None, ""):
    _ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)


logger = logging.getLogger(__name__)
FREQ_DATA_READY = False
_FREQ_TABLE: Optional[Dict[str, int]] = None
_FREQ_TABLE_VIEW: Optional[Mapping[str, int]] = None
_LEMMAS_BY_LENGTH_DATA: Optional[Dict[int, frozenset[str]]] = None
_LEMMAS_BY_LENGTH_VIEW: Optional[Mapping[int, frozenset[str]]] = None
_EMPTY_FREQ_VIEW: Mapping[str, int] = MappingProxyType({})
_EMPTY_LEMMA_VIEW: Mapping[int, frozenset[str]] = MappingProxyType({})
_SAFE_SUFFIXES = (
    "たくなかった",
    "くなかった",
    "たくない",
    "なかった",
    "ていない",
    "られない",
    "たかった",
    "られた",
    "ていた",
    "られる",
    "ている",
    "じゃった",
    "ちゃった",
    "なくなる",
    "じゃう",
    "ちゃう",
    "ません",
    "でした",
    "ます",
    "です",
    "なくて",
    "くない",
    "たい",
    "ない",
    "かった",
)


def ensure_freq_data_ready() -> bool:
    """Ensure the frequency table is loaded once."""
    global FREQ_DATA_READY, _FREQ_TABLE, _FREQ_TABLE_VIEW, _LEMMAS_BY_LENGTH_DATA, _LEMMAS_BY_LENGTH_VIEW
    if FREQ_DATA_READY and _FREQ_TABLE is not None:
        return True
    try:
        from core.frequency import jp_freq  # noqa: WPS433 - intentional local import

        loaded = jp_freq.load() or {}
        if not isinstance(loaded, dict):
            loaded = dict(loaded)
        freq_dict: Dict[str, int] = {}
        for lemma, rank in loaded.items():
            if not isinstance(lemma, str) or not lemma:
                continue
            try:
                freq_dict[lemma] = int(rank)
            except (TypeError, ValueError):
                continue
        _FREQ_TABLE = freq_dict
        _FREQ_TABLE_VIEW = MappingProxyType(freq_dict)
        _LEMMAS_BY_LENGTH_DATA = None
        _LEMMAS_BY_LENGTH_VIEW = None
        FREQ_DATA_READY = True
        return True
    except Exception:
        FREQ_DATA_READY = False
        logger.exception("Failed to load frequency data")
        return False


def annotate_tokens(tokens: List[Any]) -> List[Any]:
    """Annotate each token with a freq_rank attribute using the JP frequency table."""
    if not ensure_freq_data_ready():
        return tokens
    if not tokens:
        return tokens

    try:
        freq = get_freq_table()
        for token in tokens:
            surface = getattr(token, "surface", "") or ""
            rank = freq.get(surface)
            if rank is None:
                normalized = _normalize(surface, freq)
                if normalized:
                    rank = freq.get(normalized)
            if rank is None:
                lemma = getattr(token, "lemma", None)
                if lemma:
                    rank = freq.get(lemma)
            setattr(token, "freq_rank", rank)
        return tokens
    except Exception:
        global FREQ_DATA_READY
        FREQ_DATA_READY = False
        logger.exception("Frequency annotation failed")
        return tokens


def get_freq_table() -> Mapping[str, int]:
    """Expose the cached frequency table as a read-only mapping."""
    if not ensure_freq_data_ready():
        return _EMPTY_FREQ_VIEW
    return _FREQ_TABLE_VIEW or _EMPTY_FREQ_VIEW


def get_lemmas_by_length() -> Mapping[int, frozenset[str]]:
    """Return lemma buckets keyed by length, built once from freq data."""
    global _LEMMAS_BY_LENGTH_DATA, _LEMMAS_BY_LENGTH_VIEW
    if not ensure_freq_data_ready():
        return _EMPTY_LEMMA_VIEW
    if _LEMMAS_BY_LENGTH_VIEW is not None:
        return _LEMMAS_BY_LENGTH_VIEW

    freq = _FREQ_TABLE or {}
    buckets: Dict[int, set[str]] = {}
    for lemma in freq.keys():
        length = len(lemma)
        if length <= 0:
            continue
        bucket = buckets.setdefault(length, set())
        bucket.add(lemma)

    lemma_data: Dict[int, frozenset[str]] = {
        length: frozenset(values) for length, values in buckets.items()
    }
    _LEMMAS_BY_LENGTH_DATA = lemma_data
    _LEMMAS_BY_LENGTH_VIEW = MappingProxyType(lemma_data)
    return _LEMMAS_BY_LENGTH_VIEW


def _normalize(surface: str, freq: Mapping[str, int]) -> str | None:
    """Return a safe lemma candidate by removing a single known suffix."""
    if not surface:
        return None
    for suffix in _SAFE_SUFFIXES:
        if not surface.endswith(suffix):
            continue
        candidate = surface[: -len(suffix)] if suffix else surface
        if not candidate:
            continue
        if len(candidate) < 2 and candidate not in freq:
            continue
        if candidate in freq:
            return candidate
    return None


if __name__ == "__main__":
    class T:
        pass

    a = T()
    a.surface = "する"
    a.lemma = "する"

    b = T()
    b.surface = "未知語"
    b.lemma = None

    out = annotate_tokens([a, b])
    print("a.freq_rank =", out[0].freq_rank)
    print("b.freq_rank =", out[1].freq_rank)
