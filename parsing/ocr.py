"""Station 1: PDF -> raw text.

Input : path to a scanned PDF.
Output: one raw, noisy string. No cleaning happens here (that is the next step).
"""
from abc import ABC, abstractmethod
from pathlib import Path

import pytesseract
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
from pytesseract import TesseractError, TesseractNotFoundError

from config.rules import (
    OCR_DPI,
    OCR_LANGUAGES,
    OCR_PAGE_SEPARATOR,
    OCR_TESSERACT_CONFIG,
)
from domain.exceptions import OcrError


class TextExtractor(ABC):
    """What the rest of the program knows about OCR: give a PDF, get text.

    Anything that depends on text extraction should depend on this interface,
    not on Tesseract. That lets us swap the engine without touching other code.
    """

    @abstractmethod
    def extract(self, pdf_path: Path) -> str:
        """Return the raw text of every page in the PDF."""


class TesseractTextExtractor(TextExtractor):
    """pdf2image turns each page into an image; Tesseract reads the image."""

    def __init__(
        self,
        dpi: int = OCR_DPI,
        languages: str = OCR_LANGUAGES,
        tesseract_config: str = OCR_TESSERACT_CONFIG,
    ) -> None:
        self._dpi = dpi
        self._languages = languages
        self._tesseract_config = tesseract_config

    def extract(self, pdf_path: Path) -> str:
        pdf_path = Path(pdf_path)
        if not pdf_path.is_file():
            raise OcrError(f"PDF file not found: {pdf_path}")

        try:
            pages = convert_from_path(str(pdf_path), dpi=self._dpi)
            texts = [
                pytesseract.image_to_string(
                    page, lang=self._languages, config=self._tesseract_config
                )
                for page in pages
            ]
        except (PDFInfoNotInstalledError, PDFPageCountError) as error:
            raise OcrError(f"Could not read PDF (is Poppler installed?): {error}") from error
        except (TesseractNotFoundError, TesseractError) as error:
            raise OcrError(f"Tesseract failed (installed? Hebrew pack?): {error}") from error

        return OCR_PAGE_SEPARATOR.join(texts)
