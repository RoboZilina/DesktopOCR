import argparse
import asyncio
import os
import sys

"""
Smoke commands:
  .venv\\Scripts\\python.exe tests\\test_engine_smoke.py --engine windows_ocr
  .venv\\Scripts\\python.exe tests\\test_engine_smoke.py --engine easyocr
"""

import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.engine_manager import EngineManager


def _build_synthetic_frame() -> np.ndarray:
    frame = np.full((260, 900, 3), 255, dtype=np.uint8)
    cv2.putText(frame, "HELLO 123 OCR TEST", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, "LINE TWO 456", (20, 190), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 3, cv2.LINE_AA)
    return frame


async def _run_smoke(engine_id: str) -> int:
    manager = EngineManager(
        "models/paddle",
        {
            "det": "PP-OCRv5_server_det_infer.onnx",
            "rec": "PP-OCRv5_server_rec_infer.onnx",
            "dict": "japan_dict.txt",
        },
    )

    try:
        switched = await manager.switch_engine(engine_id)
        print(f"switch_ok={switched} current={manager.current_id}")
        if not switched:
            return 2

        frame = _build_synthetic_frame()
        result = await manager.run_ocr(frame)
        text = str(result.get("text", "") or "")
        meta = result.get("meta", {}) if isinstance(result, dict) else {}

        print("text_repr=", repr(text))
        print("meta=", meta)

        warning = str(meta.get("warning", "") or "")
        if (
            warning.startswith("windows_ocr_unavailable")
            or warning.startswith("easyocr_not_loaded")
            or "dependency missing" in warning
        ):
            return 3
        return 0
    finally:
        await manager.dispose_all()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual smoke test for DesktopOCR engines")
    parser.add_argument("--engine", choices=["windows_ocr", "easyocr"], required=True)
    args = parser.parse_args()

    return asyncio.run(_run_smoke(args.engine))


if __name__ == "__main__":
    raise SystemExit(main())
