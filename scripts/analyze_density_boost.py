from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DENSITY_DROP_RE = re.compile(
    r"\[Prune\]\s+box#(?P<idx>\d+)\s+reason=density\s+score=(?P<score>[^\s]+)\s+area_ratio=(?P<area>[^\s]+)\s+density=(?P<density>[^\s]+)",
)
SUSPECT_RE = re.compile(
    r"\[PruneSuspect\]\s+box#(?P<idx>\d+)\s+density=(?P<density>[^\s]+)\s+area_ratio=(?P<area>[^\s]+)\s+score=(?P<score>[^\s]+)",
)
BOOST_RE = re.compile(
    r"\[BoostCandidate\]\s+box=(?P<box>\[[^\]]+\])\s+area_ratio=(?P<area>[^\s]+)",
)
FINAL_RE = re.compile(r"\[Final\]\s*(?P<text>.*)")


def parse_log(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {
        "density_drops": [],
        "suspect_density": [],
        "boost_candidates": [],
        "final_texts": [],
    }

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:  # pragma: no cover - convenience tool
        raise SystemExit(f"Failed to read log '{path}': {exc}")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = DENSITY_DROP_RE.search(line)
        if match:
            data["density_drops"].append(
                {
                    "box": int(match.group("idx")),
                    "density": float(match.group("density")),
                    "area_ratio": float(match.group("area")),
                    "score": match.group("score"),
                    "raw": line,
                }
            )
            continue

        match = SUSPECT_RE.search(line)
        if match:
            score = match.group("score")
            data["suspect_density"].append(
                {
                    "box": int(match.group("idx")),
                    "density": float(match.group("density")),
                    "area_ratio": float(match.group("area")),
                    "score": None if score == "n/a" else float(score),
                    "raw": line,
                }
            )
            continue

        match = BOOST_RE.search(line)
        if match:
            data["boost_candidates"].append(
                {
                    "box": match.group("box"),
                    "area_ratio": float(match.group("area")),
                    "raw": line,
                }
            )
            continue

        match = FINAL_RE.search(line)
        if match:
            text = match.group("text").strip()
            data["final_texts"].append(text)

    return data


def _summarize(collection: list[dict[str, Any]], label: str, max_items: int) -> None:
    print(f"{label}: {len(collection)}")
    for entry in collection[:max_items]:
        raw = entry.get("raw", "")
        print(f"  - {raw}")
    if len(collection) > max_items:
        print(f"    … {len(collection) - max_items} more")


def main() -> None:  # pragma: no cover - CLI utility
    parser = argparse.ArgumentParser(description="Summarize density drops and boost candidates from DesktopOCR logs")
    parser.add_argument("logs", nargs="+", type=Path, help="Log files produced via --debug-ocr")
    parser.add_argument("--max-items", type=int, default=10, help="Max entries per category to print")
    parser.add_argument("--json-out", type=Path, help="Optional path to write structured JSON summary")
    args = parser.parse_args()

    summaries: dict[str, Any] = {}
    for log_path in args.logs:
        if not log_path.exists():
            print(f"[warn] Log not found: {log_path}")
            continue
        print(f"=== {log_path} ===")
        summary = parse_log(log_path)
        _summarize(summary["density_drops"], "Density drops", args.max_items)
        _summarize(summary["suspect_density"], "Suspect density", args.max_items)
        _summarize(summary["boost_candidates"], "Boost candidates", args.max_items)
        _summarize(summary["final_texts"], "Final lines", args.max_items)
        print()
        summaries[str(log_path)] = summary

    if args.json_out:
        args.json_out.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote JSON summary -> {args.json_out}")


if __name__ == "__main__":
    main()
