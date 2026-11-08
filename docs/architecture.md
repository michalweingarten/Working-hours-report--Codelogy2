# Architecture

## The pipeline

```
PDF ─1─> raw text ─2─> ReportType
raw text ─3─> AttendanceReport ─4─> new AttendanceReport ─5─> HTML / PDF
```

1. **OCR** (`parsing/ocr.py`): pdf2image turns every page into an image, Tesseract reads it.
   `TextExtractor` is the interface; `TesseractTextExtractor` is the only class that imports pytesseract.
2. **Classifier** (`parsing/classifier.py`): weighted keywords (`config/report_keywords.py`).
   It returns a type only with enough evidence; otherwise it raises `ClassificationError`.
3. **Parser** (`parsing/`): `create_parser(type)` picks the class from `PARSERS`.
   `BaseParser.parse()` (Template Method) runs the shared flow; `TypeAParser` and
   `TypeBParser` read their own rows and summary.
4. **Transformation** (`transformation/`): `TransformationService` picks the strategy and
   the rules of the type from dictionaries, gives every row its own random generator,
   and checks the new report with `validation.ensure_valid_variant`.
5. **Generation** (`generation/`): `BaseRenderer` with `HtmlRenderer` and `PdfRenderer`.
   The page of each type is data: a list of blocks in `layouts.py`.

## The contract

`AttendanceReport` (`domain/models.py`): `report_type`, `header`, `rows` (a tuple of
`AttendanceRow`), `summary`. Every class is a frozen dataclass, so nothing can change a
report after it is built; the transformation builds a new one with `dataclasses.replace()`.
Type B fields (break, 100%/125%/150%, Shabbat, place) are optional and `None` in type A.

## Who may import whom

The arrows go only down:

```
main.py
  ├── parsing/          (stations 1-3)
  ├── transformation/   (station 4)
  └── generation/       (station 5)
        └── domain/ + config/
```

* `domain/` imports nothing from the project except itself.
* `config/` may import `domain/` (to name the report types).
* `generation/` never imports `parsing/` or `transformation/` (there is a test for it).
* Only `main.py` builds the strategies and renderers and hands them in (dependency injection).

## Errors

`domain/exceptions.py`: one base class `AttendanceReportError`, and one class per station
(`OcrError`, `ClassificationError`, `ParsingError`, `TransformationError`,
`ValidationError`, `GenerationError`). `main.py` catches the base class, prints one line
per failed file, and goes on.
