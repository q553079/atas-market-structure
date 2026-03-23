from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LOCAL_TMP_ROOT = ROOT / ".pytest-tmp"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LOCAL_TMP_ROOT.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def tmp_path():
    path = Path(tempfile.mkdtemp(prefix="pytest-", dir=LOCAL_TMP_ROOT))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
