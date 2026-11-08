"""Shared test helpers (pytest loads this file automatically)."""
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_ENCODING = "utf-8"


@pytest.fixture
def read_fixture():
    """read_fixture("name.txt") -> the saved OCR text stored in tests/fixtures/."""

    def _read(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding=FIXTURE_ENCODING)

    return _read
