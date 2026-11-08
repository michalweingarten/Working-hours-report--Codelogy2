"""Every number and fixed setting used by the program.

Nothing else in the code base should contain a "magic" number or a
hard-coded setting. If a value might change, it lives here.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from domain.models import ReportType

# --- Station 1: OCR ---------------------------------------------------------
# 300 DPI is the usual sweet spot for Tesseract: lower is blurry, higher is slow.
OCR_DPI: Final[int] = 300

# Tesseract language packs. "heb" reads Hebrew, "eng" reads digits and Latin letters.
OCR_LANGUAGES: Final[str] = "heb+eng"

# --psm 6 = "assume a single uniform block of text". It keeps table rows together.
OCR_TESSERACT_CONFIG: Final[str] = "--psm 6"

# Pages are joined with this separator into one raw string.
OCR_PAGE_SEPARATOR: Final[str] = "\n"

# --- Output files -----------------------------------------------------------
OUTPUT_DIR_NAME: Final[str] = "output"
RAW_TEXT_FILE_SUFFIX: Final[str] = "_raw_ocr.txt"
TEXT_FILE_ENCODING: Final[str] = "utf-8"
# --- Station 2: classifier --------------------------------------------------
# How much a keyword is worth. A strong keyword is one that appears in only one
# report type and survives OCR well.
KEYWORD_WEIGHT_STRONG: Final[int] = 3
KEYWORD_WEIGHT_MEDIUM: Final[int] = 2
KEYWORD_WEIGHT_WEAK: Final[int] = 1

# The winning type needs at least this many points, and must beat the runner-up
# by at least this margin. Otherwise the classifier refuses to guess.
CLASSIFIER_MIN_WINNING_SCORE: Final[int] = 4
CLASSIFIER_MIN_MARGIN: Final[int] = 2

# --- Station 3: parser, type A ----------------------------------------------
# A believable working day: times outside this window are OCR mistakes.
WORKDAY_EARLIEST_MINUTES: Final[int] = 5 * 60  # 05:00
WORKDAY_LATEST_MINUTES: Final[int] = 23 * 60  # 23:00
SHIFT_MIN_MINUTES: Final[int] = 15
SHIFT_MAX_MINUTES: Final[int] = 14 * 60

# OCR often drops the ":" or the "." in a number. A 3-digit number like "803" or "350"
# is read as a time of day (8:03) when its first digit is at least this, and as an
# amount of hours (3.50) otherwise. Seen in the samples: entries are 8:xx, totals 2.88-3.50.
# This is a heuristic based on the samples: if reports with 6+ hour shifts appear, revisit it.
BARE_NUMBER_TIME_MIN_FIRST_DIGIT: Final[int] = 6

# --- Station 4: transformation ----------------------------------------------
# Part of the seed of every row: a row's random numbers come from (this seed, its date),
# so two runs on the same file give the same output, and rows do not affect each other.
VARIATION_SEED: Final[int] = 42
MONEY_PRECISION_TEXT: Final[str] = "0.01"


@dataclass(frozen=True)
class TransformRules:
    """How far the times of a row may move, in minutes, in each direction.

    time_step_minutes: new times are whole multiples of this. 1 = to the minute.
    The service sets it for each report from the source itself (TIME_STEP_CANDIDATES).
    """

    entry_shift_minutes: int
    exit_shift_minutes: int
    break_shift_minutes: int = 0
    time_step_minutes: int = 1


# The new times keep the "roundness" of the source: n_r_5_n has only 8:30 and 12:00,
# n_r_10_n has 8:01 and 11:05. The step of a report is the largest of these that at
# least ROUND_TIMES_SHARE of its times are multiples of (so one OCR error, like 8:50
# instead of 8:30, does not cancel it), and not larger than the allowed shift.
TIME_STEP_CANDIDATES: Final[tuple[int, ...]] = (30, 15, 10, 5, 1)
ROUND_TIMES_SHARE: Final[float] = 0.9


# One line per report type. In type B the break stays as in the source (decision 44).
TRANSFORM_RULES: Final[Mapping[ReportType, TransformRules]] = {
    ReportType.TYPE_A: TransformRules(entry_shift_minutes=15, exit_shift_minutes=15),
    ReportType.TYPE_B: TransformRules(entry_shift_minutes=15, exit_shift_minutes=15, break_shift_minutes=0),
}

# Overtime in type B on a regular day (decision 43): up to 8 hours at 100%,
# from 8 to 9 hours at 125%, above 9 hours at 150%. The samples have no overtime at all,
# so these numbers are a choice, not something read from the reports.
REGULAR_DAY_MINUTES: Final[int] = 8 * 60
OVERTIME_125_UNTIL_MINUTES: Final[int] = 9 * 60

# --- Station 5: generation ---------------------------------------------------
# output/<name of the source>_variant.html (or .pdf)
VARIANT_NAME_SUFFIX: Final[str] = "_variant"

# Which browser prints the PDF, in this order. None = the Chromium that Playwright
# downloads; "msedge" / "chrome" = a browser already installed on the computer.
PDF_BROWSER_CHANNELS: Final[tuple[str | None, ...]] = (None, "msedge", "chrome")
