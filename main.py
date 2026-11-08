"""Entry point: builds the pieces, connects the stations, and nothing more.

  1. OCR             PDF -> raw text (also saved to output/<name>_raw_ocr.txt)
  2. Classifier      raw text -> report type
  3. Parser          raw text -> AttendanceReport
  4. Transformation  AttendanceReport -> new AttendanceReport (the original is not changed)
  5. Generation      new AttendanceReport -> output/<name>_variant.html / .pdf

Usage:  python main.py input_pdfs/n_r_5_n.pdf [more.pdf ...] [-o output] [--format html|pdf|all]
"""
import argparse
import logging
import sys
from pathlib import Path

from config.rules import OUTPUT_DIR_NAME, RAW_TEXT_FILE_SUFFIX, TEXT_FILE_ENCODING, VARIANT_NAME_SUFFIX
from domain.exceptions import AttendanceReportError
from domain.models import AttendanceReport, ReportType
from generation.html_renderer import HtmlRenderer
from generation.pdf_renderer import PdfRenderer
from parsing.classifier import ReportClassifier
from parsing.ocr import TesseractTextExtractor, TextExtractor
from parsing.parser_factory import create_parser
from transformation.service import TransformationService
from transformation.type_a_strategy import TypeATransformationStrategy
from transformation.type_b_strategy import TypeBTransformationStrategy

# The only place that builds the pieces and connects them.
TRANSFORMER = TransformationService(
    strategies={
        ReportType.TYPE_A: TypeATransformationStrategy(),
        ReportType.TYPE_B: TypeBTransformationStrategy(),
    }
)
RENDERERS = {"html": HtmlRenderer(), "pdf": PdfRenderer()}


def build_variant(raw_text: str) -> tuple[AttendanceReport, AttendanceReport]:
    """Stations 2-4 on text that was already read: (original, variant). Tested without Tesseract."""
    report_type = ReportClassifier().classify(raw_text)
    original = create_parser(report_type).parse(raw_text)
    return original, TRANSFORMER.transform(original)


def process_pdf(pdf_path: Path, output_dir: Path, formats: list[str], extractor: TextExtractor) -> list[Path]:
    raw_text = extractor.extract(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{pdf_path.stem}{RAW_TEXT_FILE_SUFFIX}").write_text(raw_text, encoding=TEXT_FILE_ENCODING)
    _original, variant = build_variant(raw_text)
    name_stem = f"{pdf_path.stem}{VARIANT_NAME_SUFFIX}"
    return [RENDERERS[f].render(variant, output_dir / f"{name_stem}{RENDERERS[f].file_extension}") for f in formats]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a logical variation of a scanned attendance report.")
    parser.add_argument("pdfs", nargs="+", type=Path, help="one or more scanned attendance reports (PDF)")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path(OUTPUT_DIR_NAME), help="default: output")
    parser.add_argument("--format", choices=[*RENDERERS, "all"], default="all", help="default: all")
    parser.add_argument("-q", "--quiet", action="store_true", help="hide the warnings about rebuilt rows")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, extractor: TextExtractor | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.ERROR if args.quiet else logging.WARNING, format="  Warning: %(message)s")
    formats = list(RENDERERS) if args.format == "all" else [args.format]
    extractor = extractor or TesseractTextExtractor()

    failed = 0
    for pdf_path in args.pdfs:
        print(f"{pdf_path.name}:")
        try:
            for saved in process_pdf(pdf_path, args.output_dir, formats, extractor):
                print(f"  Created {saved}")
        except AttendanceReportError as error:  # one clear message, then the next file
            print(f"  Failed: {error}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
