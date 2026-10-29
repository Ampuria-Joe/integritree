"""Runs the test suite with a known-good configuration.

Ignores stray pytest settings (ini files in parent folders, PYTEST_ADDOPTS, ...) that can make
pytest report "no tests ran", and prints diagnostics if nothing is collected.
Usage:  python run_tests.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
for var in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"):
    os.environ.pop(var, None)


def diagnose():
    import pytest
    print(f"\npython {sys.version.split()[0]} | pytest {pytest.__version__} | project {ROOT}")
    print("PYTEST* environment variables:", {k: v for k, v in os.environ.items() if k.startswith("PYTEST")} or "none")
    for folder in [ROOT, *ROOT.parents]:
        for name in ("pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "conftest.py"):
            if (folder / name).exists():
                print("config file found:", folder / name)
    tests = ROOT / "tests"
    print("tests folder:", sorted(f.name for f in tests.iterdir()) if tests.exists() else "MISSING")
    print("Please send this output.")


if __name__ == "__main__":
    import pytest
    code = pytest.main(["-c", str(ROOT / "pytest.ini"), "--rootdir", str(ROOT), "-o", "addopts=",
                        "-p", "no:cacheprovider", "-q", str(ROOT / "tests" / "test_pipeline.py"), *sys.argv[1:]])
    if code in (4, 5):
        print("\nNo tests could be collected.")
        diagnose()
    sys.exit(code)
