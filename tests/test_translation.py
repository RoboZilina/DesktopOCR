"""Manual test script for the translation pipeline.

Run with:  python tests/test_translation.py

No PyQt6 or UI imports -- standalone asyncio only.
All 5 tests print their result; failures print a clear message.
"""

import asyncio
import sys
import os

# Force UTF-8 output on Windows (avoids cp932 encode errors)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure project root is on the path so core.translation can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.translation.deepl_backend import DeepLBackend
from core.translation.libre_backend import LibreTranslateBackend
from core.translation.manager import TranslationManager


# ------------------------------------------------------------------------------
# Test 1 -- DeepL availability
# ------------------------------------------------------------------------------
async def test_deepl_availability():
    print("\n[Test 1] DeepL availability check...")
    backend = DeepLBackend()
    result = await backend.is_available()
    print(f"  DeepL available: {result}")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 2 -- DeepL translation
# ------------------------------------------------------------------------------
async def test_deepl_translation():
    print("\n[Test 2] DeepL translation: 'konnichiwa' (Japanese) ...")
    # Small delay so we don't immediately 429 after the availability probe
    await asyncio.sleep(1.0)
    backend = DeepLBackend()
    input_text = "\u3053\u3093\u306b\u3061\u306f"  # konnichiwa
    result = await backend.translate(input_text)
    print(f"  Input:  {input_text!r}")
    print(f"  Result: {result!r}")
    if result:
        print("  Status: PASSED")
    else:
        print("  Status: FAILED (empty result -- check internet connection)")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 3 -- LibreTranslate availability (expected False if not running)
# ------------------------------------------------------------------------------
async def test_libre_availability():
    print("\n[Test 3] LibreTranslate availability check (expected False if not running)...")
    backend = LibreTranslateBackend()
    result = await backend.is_available()
    print(f"  LibreTranslate available: {result}")
    print("  Status: PASSED (availability is informational)")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 4 -- Manager with both backends
# ------------------------------------------------------------------------------
async def test_manager_translation():
    print("\n[Test 4] Manager.translate with DeepL + LibreTranslate...")
    await asyncio.sleep(1.0)
    manager = TranslationManager([
        DeepLBackend(),
        LibreTranslateBackend(),
    ])
    input_text = "\u306a\u306e\u306b\u3001\u4eca"  # nanoni, ima
    result = await manager.translate(input_text)
    print(f"  Input:        {input_text!r}")
    print(f"  Result:       {result!r}")
    print(f"  Backend used: {manager.last_used_backend}")
    if result:
        print("  Status: PASSED")
    else:
        print("  Status: FAILED (all backends returned empty -- check internet)")
    await manager.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 5 -- Empty string handling
# ------------------------------------------------------------------------------
async def test_empty_input():
    print("\n[Test 5] Empty string handling...")
    manager = TranslationManager([
        DeepLBackend(),
        LibreTranslateBackend(),
    ])
    result = await manager.translate("")
    assert result == "", f"Expected empty string, got: {result!r}"
    print("  Empty string test: PASSED")

    result_ws = await manager.translate("   ")
    assert result_ws == "", f"Expected empty string for whitespace, got: {result_ws!r}"
    print("  Whitespace-only test: PASSED")
    await manager.dispose()


# ------------------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------------------
async def main():
    print("=" * 60)
    print("DesktopOCR Translation Pipeline -- Manual Test")
    print("=" * 60)

    await test_deepl_availability()
    await test_deepl_translation()
    await test_libre_availability()
    await test_manager_translation()
    await test_empty_input()

    print("\n" + "=" * 60)
    print("All tests complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
