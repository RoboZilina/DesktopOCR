from __future__ import annotations

import logging
import os
import sys
from typing import Any, List

if __package__ in (None, ""):
    _ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)


logger = logging.getLogger(__name__)
FREQ_DATA_READY = False


def ensure_freq_data_ready() -> bool:
    """Ensure the frequency table is loaded once."""
    global FREQ_DATA_READY
    if FREQ_DATA_READY:
        return True
    try:
        from core.frequency import jp_freq  # noqa: WPS433 - intentional local import

        jp_freq.load()
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
        from core.frequency import jp_freq  # noqa: WPS433 - intentional local import

        for token in tokens:
            surface = getattr(token, "surface", "") or ""
            rank = jp_freq.lookup(surface)
            if rank is None:
                lemma = getattr(token, "lemma", None)
                if lemma:
                    rank = jp_freq.lookup(lemma)
            setattr(token, "freq_rank", rank)
        return tokens
    except Exception:
        global FREQ_DATA_READY
        FREQ_DATA_READY = False
        logger.exception("Frequency annotation failed")
        return tokens


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
