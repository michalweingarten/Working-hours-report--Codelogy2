"""Which words give away which report type (used by parsing/classifier.py).

Each report type has a dictionary:  keyword -> weight.
Adding a new report type = adding one more entry here, nothing else changes.

How these words were picked: by reading the sample PDFs and checking, on the saved
OCR text of both Linux and Windows runs, which words actually survive OCR.
A word is only useful if it appears in ONE type and not in the other.
Words are written without quotation marks, because the classifier removes them
from the text before searching (so  סה"כ  is written  סהכ  ).
"""
from collections.abc import Mapping
from typing import Final

from config.rules import KEYWORD_WEIGHT_MEDIUM, KEYWORD_WEIGHT_STRONG, KEYWORD_WEIGHT_WEAK
from domain.models import ReportType

REPORT_KEYWORDS: Final[Mapping[ReportType, Mapping[str, int]]] = {
    # Type A, the simple report: a header box with days, monthly hours, price per hour.
    ReportType.TYPE_A: {
        "עבודה לחודש": KEYWORD_WEIGHT_STRONG,  # "total work days per month"
        "מחיר לשעה": KEYWORD_WEIGHT_STRONG,
        "כרטיס עובד": KEYWORD_WEIGHT_STRONG,
        "לתשלום": KEYWORD_WEIGHT_MEDIUM,
        "שם העובד": KEYWORD_WEIGHT_MEDIUM,
        "שעת כניסה": KEYWORD_WEIGHT_MEDIUM,
        "שעת יציאה": KEYWORD_WEIGHT_MEDIUM,
        "הערות": KEYWORD_WEIGHT_WEAK,
        "שעת": KEYWORD_WEIGHT_WEAK,
    },
    # Type B, the detailed report: break column and the 100/125/150 split.
    ReportType.TYPE_B: {
        "הפסקה": KEYWORD_WEIGHT_STRONG,
        "בונוס": KEYWORD_WEIGHT_STRONG,
        "נסיעות": KEYWORD_WEIGHT_STRONG,
        "125%": KEYWORD_WEIGHT_STRONG,
        "150%": KEYWORD_WEIGHT_STRONG,
        "שבת 150%": KEYWORD_WEIGHT_MEDIUM,
        "מקום עבודה": KEYWORD_WEIGHT_MEDIUM,
        "100%": KEYWORD_WEIGHT_WEAK,
    },
}
