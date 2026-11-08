"""Tests for parsing/classifier.py.

The texts come from tests/fixtures/: the saved OCR output of each sample PDF, from two
different machines (Linux and Windows). The two machines give different OCR text for the
same PDF, so passing on both shows the classifier does not depend on one OCR variant.
"""
import pytest

from config.report_keywords import REPORT_KEYWORDS
from domain.exceptions import ClassificationError
from domain.models import ReportType
from parsing.classifier import ReportClassifier
from tests.conftest import FIXTURES_DIR

# Every saved OCR text in tests/fixtures/ is tested. The file name says the type:
# n_r_*  = the simple report (type A),  a_r_*  = the detailed report (type B).
# A new sample report = a new fixture file, no change to this test file.
SIMPLE_REPORT_FIXTURES = sorted(p.name for p in FIXTURES_DIR.glob("n_r_*.txt"))
DETAILED_REPORT_FIXTURES = sorted(p.name for p in FIXTURES_DIR.glob("a_r_*.txt"))

STRONG_KEYWORDS_OF_TYPE_B = ["הפסקה", "בונוס", "נסיעות", "125%", "150%"]
WEAK_KEYWORDS_ONLY = "שעת הערות"


@pytest.fixture
def classifier() -> ReportClassifier:
    return ReportClassifier()


class TestSampleReports:
    @pytest.mark.parametrize("fixture_name", SIMPLE_REPORT_FIXTURES)
    def test_simple_report_is_type_a(self, classifier, read_fixture, fixture_name):
        assert classifier.classify(read_fixture(fixture_name)) is ReportType.TYPE_A

    @pytest.mark.parametrize("fixture_name", DETAILED_REPORT_FIXTURES)
    def test_detailed_report_is_type_b(self, classifier, read_fixture, fixture_name):
        assert classifier.classify(read_fixture(fixture_name)) is ReportType.TYPE_B

    @pytest.mark.parametrize("fixture_name", SIMPLE_REPORT_FIXTURES)
    def test_simple_report_has_no_evidence_for_type_b(self, classifier, read_fixture, fixture_name):
        assert classifier.score(read_fixture(fixture_name))[ReportType.TYPE_B] == 0

    @pytest.mark.parametrize("fixture_name", DETAILED_REPORT_FIXTURES)
    def test_detailed_report_has_no_evidence_for_type_a(self, classifier, read_fixture, fixture_name):
        assert classifier.score(read_fixture(fixture_name))[ReportType.TYPE_A] == 0


class TestOcrDamage:
    @pytest.mark.parametrize("damaged_word", STRONG_KEYWORDS_OF_TYPE_B)
    def test_one_damaged_keyword_does_not_change_the_result(self, classifier, read_fixture, damaged_word):
        text = read_fixture("a_r_9_linux.txt").replace(damaged_word, "xxx")
        assert classifier.classify(text) is ReportType.TYPE_B

    def test_real_ocr_damage_a_r_25_lost_the_break_column(self, classifier, read_fixture):
        # Not a made-up case: in a_r_25 the OCR lost the word "הפסקה" completely.
        text = read_fixture("a_r_25_linux.txt")
        assert classifier.score(text)[ReportType.TYPE_B] > 0
        assert "הפסקה" not in text
        assert classifier.classify(text) is ReportType.TYPE_B

    def test_there_are_at_least_two_samples_of_each_type(self):
        assert len(SIMPLE_REPORT_FIXTURES) >= 2
        assert len(DETAILED_REPORT_FIXTURES) >= 2

    def test_direction_marks_and_quote_variants_do_not_matter(self, classifier):
        noisy = chr(0x200F) + "הפ" + chr(0x200E) + "סקה בונוס נסיעות 125% 150%"
        assert classifier.classify(noisy) is ReportType.TYPE_B


class TestRefusingToGuess:
    def test_empty_text(self, classifier):
        with pytest.raises(ClassificationError):
            classifier.classify("")

    def test_text_with_no_keywords(self, classifier):
        with pytest.raises(ClassificationError):
            classifier.classify("lorem ipsum 12:30 1/9/22")

    def test_weak_evidence_only(self, classifier):
        with pytest.raises(ClassificationError):
            classifier.classify(WEAK_KEYWORDS_ONLY)

    def test_both_types_equally_likely(self, classifier, read_fixture):
        both = read_fixture("n_r_5_n_linux.txt") + read_fixture("a_r_9_linux.txt")
        scores = classifier.score(both)
        assert scores[ReportType.TYPE_A] > 0 and scores[ReportType.TYPE_B] > 0
        tight = ReportClassifier(min_margin=max(scores.values()) + 1)
        with pytest.raises(ClassificationError):
            tight.classify(both)

    def test_error_message_shows_the_scores(self, classifier):
        with pytest.raises(ClassificationError, match="TYPE_A=0"):
            classifier.classify("nothing here")


class TestConfiguration:
    def test_keywords_can_be_injected(self):
        custom = {
            ReportType.TYPE_A: {"alpha": 5},
            ReportType.TYPE_B: {"beta": 5},
        }
        custom_classifier = ReportClassifier(keywords=custom, min_winning_score=5, min_margin=1)
        assert custom_classifier.classify("beta") is ReportType.TYPE_B
        assert custom_classifier.classify("alpha") is ReportType.TYPE_A

    def test_a_keyword_counts_once_however_often_it_repeats(self, classifier):
        once = classifier.score("הפסקה")[ReportType.TYPE_B]
        many = classifier.score("הפסקה " * 50)[ReportType.TYPE_B]
        assert once == many

    def test_every_report_type_has_keywords(self):
        assert set(REPORT_KEYWORDS) == set(ReportType)
