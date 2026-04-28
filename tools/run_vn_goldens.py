import argparse
import asyncio
import json
import logging
import os
import pathlib

import cv2

from core.engine_manager import EngineManager

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_GOLDEN_DIR = pathlib.Path("tests/golden_vn_frames")
DEFAULT_OUTPUTS = pathlib.Path("tests/golden_vn_frames/expected.json")


def load_expected(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_expected(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def _run_frames(frames: list[pathlib.Path], engine_manager: EngineManager) -> dict:
    outputs: dict[str, dict] = {}
    for frame in frames:
        LOGGER.info("Processing %s", frame.name)
        img = cv2.imread(str(frame))
        if img is None:
            raise RuntimeError(f"Failed to load frame {frame}")
        result = await engine_manager.run_ocr(img)
        outputs[frame.name] = {
            "text": result.get("text", ""),
            "confidence": float(result.get("confidence", 0.0)),
        }
    return outputs


def main():
    parser = argparse.ArgumentParser(description="Run VN golden regression set")
    parser.add_argument("--golden-dir", default=str(DEFAULT_GOLDEN_DIR))
    parser.add_argument("--expected", default=str(DEFAULT_OUTPUTS))
    parser.add_argument("--update", action="store_true", help="Update stored outputs instead of diffing")
    args = parser.parse_args()

    os.environ["DESKTOCR_VN_STABLE_MODE"] = "1"

    golden_dir = pathlib.Path(args.golden_dir)
    expected_path = pathlib.Path(args.expected)

    frames = sorted(golden_dir.glob("*.png"))
    if not frames:
        LOGGER.warning("No golden frames found under %s", golden_dir)
        return

    engine_manager = EngineManager("models/paddle", {"det": "det.onnx", "rec": "rec.onnx", "dict": "japan_dict.txt"})

    outputs = asyncio.run(_run_frames(frames, engine_manager))

    if args.update:
        save_expected(expected_path, outputs)
        LOGGER.info("Updated golden outputs (%s)", expected_path)
        return

    expected = load_expected(expected_path)
    mismatches = []
    for name, data in outputs.items():
        expected_data = expected.get(name)
        if not expected_data:
            mismatches.append((name, "missing expected"))
            continue
        if data["text"] != expected_data.get("text"):
            mismatches.append((name, "text"))
            continue
        if abs(float(data["confidence"]) - float(expected_data.get("confidence", 0.0))) > 0.05:
            mismatches.append((name, "confidence"))

    if mismatches:
        LOGGER.error("Golden mismatches detected:")
        for name, reason in mismatches:
            LOGGER.error("- %s: %s", name, reason)
        raise SystemExit(1)

    LOGGER.info("All golden frames passed")


if __name__ == "__main__":
    main()
