"""Smoke-test the ArgosTranslate backend with bundled model."""
import os
import sys

sys.path.insert(0, ".")

import asyncio

from core.translation.argos_backend import ArgosTranslatorBackend


async def main():
    backend = ArgosTranslatorBackend()

    # 1. Check bundled model path
    model_path = backend._bundled_model_path()
    print(f"Bundled model path: {model_path}", flush=True)

    print(f"File exists: {os.path.isfile(model_path)}", flush=True)
    assert os.path.isfile(model_path), f"Bundled model not found at {model_path}"

    # 2. Test is_available (cheap file-exists check, no installation)
    avail = await backend.is_available()
    print(f"is_available: {avail}", flush=True)
    assert avail is True, "is_available() should return True when model file exists"

    # 3. Test translate (JA→EN)
    result = await backend.translate("これはテストです。", "ja", "en")
    print(f"Translate 'これはテストです。': {result!r}", flush=True)
    assert result, "Translation should return non-empty string"
    assert "test" in result.lower(), f"Expected 'test' in translation, got: {result!r}"

    # 4. Test empty text
    result = await backend.translate("", "ja", "en")
    print(f"Translate '': {result!r}", flush=True)
    assert result == "", "Empty input should return empty string"

    # 5. Test whitespace-only
    result = await backend.translate("   ", "ja", "en")
    print(f"Translate '   ': {result!r}", flush=True)
    assert result == "", "Whitespace-only input should return empty string"

    # 6. Test unsupported pair
    result = await backend.translate("hello", "en", "ja")
    print(f"Translate EN→JA: {result!r}", flush=True)
    assert result == "", "Unsupported language pair should return empty string"

    # 7. Test is_available does NOT trigger installation side effects
    #    (calling it before translate should not install the model)
    backend2 = ArgosTranslatorBackend()
    avail2 = await backend2.is_available()
    assert avail2 is True, "is_available should not require model installation"
    assert backend2._installed is False, "is_available must not trigger installation"
    await backend2.dispose()

    # Cleanup
    await backend.dispose()

    print("\nALL TESTS PASSED", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
