"""The stations together, and main.py as a command line tool. No Tesseract needed:
a fake extractor hands in the saved OCR text of the samples."""
from pathlib import Path

import pytest

from domain.exceptions import OcrError
from generation.html_renderer import HtmlRenderer
from main import build_variant, main
from parsing.ocr import TextExtractor
from tests.conftest import FIXTURES_DIR
from transformation.validation import report_violations

TYPE_A_FIXTURES = sorted(p.name for p in FIXTURES_DIR.glob("n_r_*.txt"))


class SavedTextExtractor(TextExtractor):
    """Instead of OCR: <name>.pdf -> the saved text tests/fixtures/<name>_linux.txt."""

    def extract(self, pdf_path: Path) -> str:
        fixture = FIXTURES_DIR / f"{Path(pdf_path).stem}_linux.txt"
        if not fixture.is_file():
            raise OcrError(f"PDF file not found: {pdf_path}")
        return fixture.read_text(encoding="utf-8")


@pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
def test_type_a_end_to_end(read_fixture, fixture_name):
    original, variant = build_variant(read_fixture(fixture_name))
    assert variant != original
    assert len(variant.rows) == len(original.rows)


@pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
def test_variant_keeps_every_rule(read_fixture, fixture_name):
    _original, variant = build_variant(read_fixture(fixture_name))
    assert report_violations(variant) == []


@pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
def test_two_runs_give_the_same_html(read_fixture, fixture_name):
    text = read_fixture(fixture_name)
    first, second = build_variant(text)[1], build_variant(text)[1]
    assert HtmlRenderer().to_html(first) == HtmlRenderer().to_html(second)


ALL_FIXTURES = sorted(p.name for p in FIXTURES_DIR.glob("*.txt"))


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_every_sample_goes_through_every_station(read_fixture, fixture_name):
    original, variant = build_variant(read_fixture(fixture_name))
    assert variant.report_type is original.report_type
    assert report_violations(variant) == []
    assert HtmlRenderer().to_html(variant).startswith("<!DOCTYPE html>")


def test_type_b_end_to_end_keeps_the_break_and_the_shabbat_column(read_fixture):
    original, variant = build_variant(read_fixture("a_r_9_linux.txt"))
    assert all(row.break_minutes == 30 for row in variant.rows)
    for row in variant.rows:
        if row.row_date.weekday() == 5:
            assert row.shabbat_minutes == row.total_minutes


class TestCommandLine:
    def test_help_works(self, capsys):
        with pytest.raises(SystemExit) as finished:
            main(["--help"])
        assert finished.value.code == 0
        assert "--output-dir" in capsys.readouterr().out

    def test_creates_the_output_in_the_chosen_folder(self, tmp_path):
        code = main(["n_r_5_n.pdf", "-o", str(tmp_path), "--format", "html", "-q"], SavedTextExtractor())
        assert code == 0
        assert (tmp_path / "n_r_5_n_variant.html").is_file()
        assert (tmp_path / "n_r_5_n_raw_ocr.txt").is_file()

    def test_a_bad_file_gets_a_clear_message_and_the_others_still_run(self, tmp_path, capsys):
        code = main(["missing.pdf", "n_r_10_n.pdf", "-o", str(tmp_path), "--format", "html", "-q"],
                    SavedTextExtractor())
        out = capsys.readouterr().out
        assert code == 1
        assert "Failed: PDF file not found" in out and "Traceback" not in out
        assert (tmp_path / "n_r_10_n_variant.html").is_file()
