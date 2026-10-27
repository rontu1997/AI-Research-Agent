"""Fitness tests for the layering rules of ARCH §4.3 (enforced by import-linter)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_import_linter_contracts_hold() -> None:
    exe = Path(sys.executable).parent / (
        "lint-imports.exe" if sys.platform == "win32" else "lint-imports"
    )
    result = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_core_models_performs_no_io_imports() -> None:
    text = (ROOT / "core" / "models.py").read_text(encoding="utf-8")
    for banned in ("import os", "import socket", "import subprocess", "pathlib", "httpx", "open("):
        assert banned not in text
