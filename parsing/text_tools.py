"""Small text helpers shared by the classifier and both parsers.

1. Cleaning the noise that OCR (and Hebrew right-to-left text) adds.
2. Finding values inside a noisy line by PATTERN, never by column position
   (OCR on different machines puts the columns in a different order).
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from config.rules import BARE_NUMBER_TIME_MIN_FIRST_DIGIT
from domain.exceptions import TimeConversionError
from domain.time_math import clock_to_minutes, decimal_hours_to_minutes

# Invisible direction marks that Tesseract inserts around Hebrew text. They break
# word searches because  "שבת"  and  "‏שבת‎"  are different strings.
_DIRECTION_MARK_CODES: Final[tuple[int, ...]] = (
    0x200E, 0x200F,  # left-to-right / right-to-left mark
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,  # embedding and override marks
    0x2066, 0x2067, 0x2068, 0x2069,  # isolate marks
)
# All the kinds of quotation marks OCR may produce for the "  in  סה"כ.
_QUOTE_CODES: Final[tuple[int, ...]] = (
    0x22,  # "
    0x27,  # '
    0x5F3,  # Hebrew geresh
    0x5F4,  # Hebrew gershayim
    0x201C, 0x201D,  # curly double quotes
)

_DIRECTION_MARKS: Final[re.Pattern[str]] = re.compile(
    "[" + "".join(chr(code) for code in _DIRECTION_MARK_CODES) + "]"
)
_QUOTES: Final[re.Pattern[str]] = re.compile("[" + "".join(chr(code) for code in _QUOTE_CODES) + "]")

# --- patterns for values inside a line ----------------------------------------
# Day and month are taken as written; checking them is the parser's job.
# A date like 1/9/22 (type A) or 02/10/2022 (type B).
_DATE: Final[re.Pattern[str]] = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?!\d)")
# A time with a colon: 8:30, 12:00.
_CLOCK: Final[re.Pattern[str]] = re.compile(r"(?<![\d/])(\d{1,2}):(\d{2})(?![\d/])")
# An amount of hours with a dot: 3.50.
_HOURS: Final[re.Pattern[str]] = re.compile(r"(?<![\d/.:])(\d{1,2})\.(\d{2})(?![\d/.:])")
# A number that lost its ":" or ".":  1200, 803, 350, 12000.
_BARE_NUMBER: Final[re.Pattern[str]] = re.compile(r"(?<![\d/.:])(\d{3,5})(?![\d/.:])")

_FOUR_DIGITS: Final[int] = 4
_FIVE_DIGITS: Final[int] = 5
_THREE_DIGITS: Final[int] = 3
_LOST_COLON_AS_ZERO: Final[str] = "0"  # "12000": the ":" in 12:00 was read as 0


@dataclass(frozen=True)
class DateParts:
    """A date as written in the text, before anyone checked that it makes sense."""

    day: int
    month: int
    year: int  # full year: 22 -> 2022


@dataclass(frozen=True)
class LineNumbers:
    """Everything that looks like a time or an amount of hours in one line."""

    clock_times: tuple[int, ...]  # minutes since midnight, in the order found
    hour_amounts: tuple[int, ...]  # minutes


def clean_text(raw_text: str) -> str:
    """Remove direction marks and quotation marks, and squeeze repeated spaces in each line.

    Line breaks are kept, because the parsers need to read the text line by line.
    """
    text = _DIRECTION_MARKS.sub("", raw_text)
    text = _QUOTES.sub("", text)
    return "\n".join(" ".join(line.split()) for line in text.splitlines())


def flatten_text(raw_text: str) -> str:
    """Like clean_text, but everything on one line. Good for "is this word anywhere?"."""
    return " ".join(clean_text(raw_text).split())


def find_dates(line: str) -> list[DateParts]:
    """'| 1/9/22 | חמישי |' -> [DateParts(1, 9, 2022)]."""
    return [
        DateParts(day=int(day), month=int(month), year=int(year) if len(year) == 4 else 2000 + int(year))
        for day, month, year in _DATE.findall(line)
    ]


def find_numbers(line: str) -> LineNumbers:
    """Find times of day and amounts of hours, also when OCR dropped the ':' or '.'.

    Dates are removed first, so their digits are not mistaken for times.
    """
    line = _DATE.sub(" ", line)
    clock_times: list[int] = []
    hour_amounts: list[int] = []

    for hour, minute in _CLOCK.findall(line):
        _append_clock(clock_times, int(hour), int(minute))
    for whole, fraction in _HOURS.findall(line):
        hour_amounts.append(decimal_hours_to_minutes(Decimal(f"{whole}.{fraction}")))
    for digits in _BARE_NUMBER.findall(line):
        _read_bare_number(digits, clock_times, hour_amounts)

    return LineNumbers(tuple(clock_times), tuple(m for m in hour_amounts if m > 0))


def _read_bare_number(digits: str, clock_times: list[int], hour_amounts: list[int]) -> None:
    if len(digits) == _FIVE_DIGITS and digits[2] == _LOST_COLON_AS_ZERO:  # 12000 -> 12:00
        _append_clock(clock_times, int(digits[:2]), int(digits[3:]))
    elif len(digits) == _FOUR_DIGITS:  # 1200 -> 12:00
        _append_clock(clock_times, int(digits[:2]), int(digits[2:]))
    elif len(digits) == _THREE_DIGITS:
        if int(digits[0]) >= BARE_NUMBER_TIME_MIN_FIRST_DIGIT:  # 803 -> 8:03
            _append_clock(clock_times, int(digits[0]), int(digits[1:]))
        else:  # 350 -> 3.50 hours
            hour_amounts.append(decimal_hours_to_minutes(Decimal(f"{digits[0]}.{digits[1:]}")))


def _append_clock(clock_times: list[int], hour: int, minute: int) -> None:
    try:
        clock_times.append(clock_to_minutes(hour, minute))
    except TimeConversionError:
        pass  # 10:67 is not a time; OCR noise is expected, so it is simply skipped


# --- type B: values read by their POSITION in the line ------------------------
# The times and amounts of a type B row are read in column order: entry, exit, break /
# total, 100%, ... The OCR sometimes writes a whole line reversed (a_r_25 on Windows),
# so the parser first finds the direction of the line (type_b_parser.py).
_HOURS_OR_BARE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d/:.,])(\d{1,3})\.(\d{2})(?![\d/:.,])"  # 6.50, 143.00
    r"|(?<![\d/:.,])(\d)(\d{2})(?![\d/:.,])"  # 650, 000: the "." was lost
)

# Day names, by date.weekday() (Monday = 0).
_DAY_NAMES: Final[dict[str, int]] = {
    "שני": 0, "שלישי": 1, "רביעי": 2, "חמישי": 3, "שישי": 4, "שבת": 5, "ראשון": 6,
}
# How OCR writes some day names in type B, seen again and again in the real output
# (docs/ocr_notes.md). Only names that always meant the same day are here:
#   nw   -> Monday   (20/2/23, 27/2/23, 17/10/22, 31/10/22)
#   wow  -> Tuesday  (7/2/23, 14/2/23, 11/10/22, 25/10/22)
#   yan  -> Wednesday (15/2/23, 22/2/23);  wan -> Wednesday (1/2/23)
#   wn   -> Thursday (23/2/23)
# "ww" is not here: it was seen on both a Tuesday and a Friday.
_DAY_NAME_OCR_ALIASES: Final[dict[str, int]] = {"nw": 0, "wow": 1, "yan": 2, "wan": 2, "wn": 3}
_TOKEN_NOISE: Final[str] = "‘’'`|[](){},;:"


def find_clock_times(line: str) -> list[int]:
    """Times written with a colon, in the order they appear: '08:00 15:00 00:30' -> [480, 900, 30]."""
    times: list[int] = []
    for hour, minute in _CLOCK.findall(_DATE.sub(" ", line)):
        _append_clock(times, int(hour), int(minute))
    return times


def find_hour_amounts(line: str, side: str = "after") -> list[int]:
    """Amounts of hours in the order they appear, in minutes: '6.50 650 0.00' -> [390, 390, 0].

    side="after":  only the part AFTER the last clock time (the amounts columns of a row
                   read right to left; noise before the times, like "₪004", is skipped).
    side="before": only the part BEFORE the first clock time (a row the OCR wrote reversed).
    side="all":    the whole line, without its dates and clock times.
    """
    line = _DATE.sub(" ", line)
    clock_matches = list(_CLOCK.finditer(line))
    if clock_matches and side == "after":
        line = line[clock_matches[-1].end():]
    elif clock_matches and side == "before":
        line = line[:clock_matches[0].start()]
    line = _CLOCK.sub(" ", line)
    amounts: list[int] = []
    for whole, fraction, bare_whole, bare_fraction in _HOURS_OR_BARE.findall(line):
        text = f"{whole}.{fraction}" if whole else f"{bare_whole}.{bare_fraction}"
        amounts.append(decimal_hours_to_minutes(Decimal(text)))
    return amounts


def find_weekday(line: str) -> int | None:
    """The day name in a line, as date.weekday(); None if no day name could be read."""
    for raw_token in line.split():
        token = raw_token.strip(_TOKEN_NOISE)
        if token in _DAY_NAMES:
            return _DAY_NAMES[token]
        if token.lower() in _DAY_NAME_OCR_ALIASES:
            return _DAY_NAME_OCR_ALIASES[token.lower()]
    return None
