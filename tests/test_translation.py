"""Manual test script for the translation pipeline.

Run with:  python tests/test_translation.py

No PyQt6 or UI imports -- standalone asyncio only.
Tests the active backend chain: Google → MyMemory → ArgosTranslate.
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

from core.translation.google_backend import GoogleTranslateBackend
from core.translation.mymemory_backend import MyMemoryBackend
from core.translation.argos_backend import ArgosTranslatorBackend
from core.translation.manager import TranslationManager

SAMPLE_TEXT = "これはテストです。"


# ------------------------------------------------------------------------------
# Test 1 -- Google availability
# ------------------------------------------------------------------------------
async def test_google_availability():
    print("\n[Test 1] Google Translate availability check (needs internet)...")
    backend = GoogleTranslateBackend()
    result = await backend.is_available()
    print(f"  Google available: {result}")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 2 -- Google translation
# ------------------------------------------------------------------------------
async def test_google_translation():
    print(f"\n[Test 2] Google Translate: {SAMPLE_TEXT!r} ...")
    await asyncio.sleep(0.5)
    backend = GoogleTranslateBackend()
    result = await backend.translate(SAMPLE_TEXT)
    print(f"  Result: {result!r}")
    if result:
        print("  Status: PASSED")
    else:
        print("  Status: SKIPPED (no internet -- expected offline)")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 3 -- MyMemory availability
# ------------------------------------------------------------------------------
async def test_mymemory_availability():
    print("\n[Test 3] MyMemory availability check (needs internet)...")
    backend = MyMemoryBackend()
    result = await backend.is_available()
    print(f"  MyMemory available: {result}")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 4 -- MyMemory translation
# ------------------------------------------------------------------------------
async def test_mymemory_translation():
    print(f"\n[Test 4] MyMemory Translate: {SAMPLE_TEXT!r} ...")
    await asyncio.sleep(0.5)
    backend = MyMemoryBackend()
    result = await backend.translate(SAMPLE_TEXT)
    print(f"  Result: {result!r}")
    if result:
        print("  Status: PASSED")
    else:
        print("  Status: SKIPPED (no internet -- expected offline)")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 5 -- Argos availability (offline, should always pass)
# ------------------------------------------------------------------------------
async def test_argos_availability():
    print("\n[Test 5] ArgosTranslate availability (offline -- bundled model)...")
    backend = ArgosTranslatorBackend()
    result = await backend.is_available()
    print(f"  Argos available: {result}")
    assert result, "Argos bundled model should always be available"
    print("  Status: PASSED")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 6 -- Argos translation (offline, uses bundled model)
# ------------------------------------------------------------------------------
async def test_argos_translation():
    print(f"\n[Test 6] ArgosTranslate: {SAMPLE_TEXT!r} ...")
    backend = ArgosTranslatorBackend()
    result = await backend.translate(SAMPLE_TEXT)
    print(f"  Result: {result!r}")
    assert result, "Argos translation should return non-empty result"
    assert "test" in result.lower(), f"Expected 'test' in translation: {result!r}"
    print("  Status: PASSED")
    await backend.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 7 -- Manager with active backend chain
# ------------------------------------------------------------------------------
async def test_manager_translation():
    print("\n[Test 7] Manager.translate with Google + MyMemory + Argos...")
    await asyncio.sleep(0.5)
    manager = TranslationManager([
        GoogleTranslateBackend(),
        MyMemoryBackend(),
        ArgosTranslatorBackend(),
    ])
    result = await manager.translate(SAMPLE_TEXT)
    print(f"  Input:        {SAMPLE_TEXT!r}")
    print(f"  Result:       {result!r}")
    print(f"  Backend used: {manager.last_used_backend}")
    # At minimum, Argos should succeed (offline fallback)
    assert result, "Manager should return translation (Argos is offline fallback)"
    print("  Status: PASSED")
    await manager.dispose()
    return result


# ------------------------------------------------------------------------------
# Test 8 -- Empty string handling
# ------------------------------------------------------------------------------
async def test_empty_input():
    print("\n[Test 8] Empty string handling...")
    manager = TranslationManager([
        GoogleTranslateBackend(),
        MyMemoryBackend(),
        ArgosTranslatorBackend(),
    ])
    result = await manager.translate("")
    assert result == "", f"Expected empty string, got: {result!r}"
    print("  Empty string test: PASSED")

    result_ws = await manager.translate("   ")
    assert result_ws == "", f"Expected empty string for whitespace, got: {result_ws!r}"
    print("  Whitespace-only test: PASSED")

    # Verify no backend was used for empty input
    print(f"  Backend used for empty input: {manager.last_used_backend}")
    await manager.dispose()


# ------------------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------------------
async def main():
    print("=" * 60)
    print("DesktopOCR Translation Pipeline -- Manual Test")
    print("=" * 60)

    results: dict[str, bool] = {}

    results["google_avail"] = await test_google_availability()
    results["google_trans"] = bool(await test_google_translation())
    results["mymemory_avail"] = await test_mymemory_availability()
    results["mymemory_trans"] = bool(await test_mymemory_translation())
    results["argos_avail"] = await test_argos_availability()
    results["argos_trans"] = bool(await test_argos_translation())
    await test_manager_translation()
    await test_empty_input()

    print("\n" + "=" * 60)
    print("Summary:")
    for k, v in results.items():
        status = "✅" if v else "⚠️"
        print(f"  {status} {k}: {v}")
    print("=" * 60)
    print("All tests complete.")


if __name__ == "__main__":
    asyncio.run(main())
