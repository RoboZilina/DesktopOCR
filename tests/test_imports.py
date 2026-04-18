"""
tests/test_imports.py
Import smoke-test: attempts to import each core module and reports success or failure.
Run from the repo root: py -3 tests/test_imports.py
Do NOT fix errors here — this file is read-only diagnostic output.
"""

import importlib
import os
import sys
import traceback

# Ensure the repo root is on sys.path regardless of where the script is invoked from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MODULES = [
    "core.capture",
    "core.ocr_engine",
    "core.tensor_utils",
    "core.engine_manager",
    "core.windows_ocr",
    "core.vision",
    "logic.validator",
]

WIDTH = 28
OK    = "[OK]  "
FAIL  = "[FAIL]"

print(f"\n{'Module':<{WIDTH}}  Result")
print("-" * 60)

results = {}
for mod in MODULES:
    try:
        importlib.import_module(mod)
        results[mod] = (True, None)
        print(f"{mod:<{WIDTH}}  {OK}")
    except Exception as exc:
        results[mod] = (False, exc)
        # Print just the last line of the traceback for readability
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        summary = tb_lines[-1].strip()
        print(f"{mod:<{WIDTH}}  {FAIL}  —  {summary}")

print("-" * 60)
passed = sum(1 for ok, _ in results.values() if ok)
print(f"\n{passed}/{len(MODULES)} modules imported successfully.\n")

# Print full tracebacks for failed modules
failed = [(m, exc) for m, (ok, exc) in results.items() if not ok]
if failed:
    print("=" * 60)
    print("FULL TRACEBACKS")
    print("=" * 60)
    for mod, exc in failed:
        print(f"\n--- {mod} ---")
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stdout)

sys.exit(0 if not failed else 1)
