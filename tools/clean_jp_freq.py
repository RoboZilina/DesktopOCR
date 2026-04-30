import os
from typing import Dict, List, Tuple


def load_raw_freq(path: str) -> List[Tuple[str, int]]:
    entries: List[Tuple[str, int]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            header_skipped = False
            for line in fh:
                if not header_skipped:
                    header_skipped = True
                    continue
                if not line:
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                lemma = parts[0].strip()
                count_str = parts[2].strip()
                if not lemma:
                    continue
                try:
                    count = int(count_str)
                except ValueError:
                    continue
                entries.append((lemma, count))
    except FileNotFoundError:
        pass
    return entries


def _contains_ascii_letters(text: str) -> bool:
    for ch in text:
        if "A" <= ch <= "Z" or "a" <= ch <= "z":
            return True
    return False


def _is_japanese_char(ch: str) -> bool:
    code = ord(ch)
    if 0x3040 <= code <= 0x309F:  # Hiragana
        return True
    if 0x30A0 <= code <= 0x30FF:  # Katakana
        return True
    if 0xFF66 <= code <= 0xFF9D:  # Half-width katakana
        return True
    if 0x3400 <= code <= 0x4DBF:  # CJK Unified Ideographs Extension A
        return True
    if 0x4E00 <= code <= 0x9FFF:  # CJK Unified Ideographs
        return True
    return False


def clean_entries(entries: List[Tuple[str, int]]) -> Dict[str, int]:
    freq: Dict[str, int] = {}
    for lemma, count in entries:
        norm = lemma.strip()
        if not norm:
            continue
        if _contains_ascii_letters(norm):
            continue
        if norm.isdigit():
            continue
        if len(norm) == 1 and not _is_japanese_char(norm):
            continue
        freq[norm] = freq.get(norm, 0) + count
    return freq


def write_ranked_freq(freq: Dict[str, int], path: str) -> None:
    items = sorted(freq.items(), key=lambda item: (-item[1], item[0]))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        for rank, (lemma, _count) in enumerate(items, start=1):
            fh.write(f"{lemma}\t{rank}\n")


def main() -> None:
    raw_path = os.path.join("tools", "wordfreq_tatoeba_raw.tsv")
    out_dir = "resources"
    out_path = os.path.join(out_dir, "jp_freq.tsv")

    if not os.path.exists(raw_path):
        print(f"Input file not found: {raw_path}")
        return

    os.makedirs(out_dir, exist_ok=True)

    entries = load_raw_freq(raw_path)
    freq = clean_entries(entries)
    write_ranked_freq(freq, out_path)
    print(f"Wrote cleaned frequency file: {out_path} (lemmas: {len(freq)})")


if __name__ == "__main__":
    main()
