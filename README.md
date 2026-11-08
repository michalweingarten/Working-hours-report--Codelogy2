# Attendance Report Generator

Reads a scanned attendance report (PDF), and creates a new report that looks like the
original but has different hours, while everything stays logical: every exit is after
its entry, every total adds up, and overtime is split correctly.

Two report types are supported:

| | Type A: the simple report | Type B: the detailed report |
|---|---|---|
| Samples | `n_r_5_n.pdf`, `n_r_10_n.pdf` | `a_r_9.pdf`, `a_r_25.pdf` |
| Columns | date, weekday, entry, exit, total, notes | date, day, place, entry, exit, break, total, 100%, 125%, 150%, Shabbat |
| Summary | above the table: days, hours, hourly rate, pay | under the table: a totals row and a small box |

---

## Quick start

```bash
python main.py input_pdfs/n_r_5_n.pdf
```

The new report is written to `output/n_r_5_n_variant.pdf` (and `.html`).
The source file is never changed.

More options:

```bash
# several files at once
python main.py input_pdfs/n_r_5_n.pdf input_pdfs/a_r_9.pdf

# HTML only, into another folder
python main.py input_pdfs/a_r_25.pdf --format html -o my_output

# without the warnings about rows that the OCR could not read
python main.py input_pdfs/n_r_10_n.pdf -q

# all the options
python main.py --help
```

If one file fails, the program prints one clear line for it and goes on with the next
file. The exit code is 1 if any file failed.

---

## Installation

### 1. Python

Python 3.10 or newer (developed on 3.13). From the project folder:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux / macOS
pip install -r requirements.txt
```

### 2. Tesseract OCR, with Hebrew

The PDFs are scans (images), so the text is read by Tesseract.

* **Windows:** install Tesseract from the UB Mannheim build
  (https://github.com/UB-Mannheim/tesseract/wiki). In the installer, under
  *Additional language data*, select **Hebrew**. Add the install folder
  (usually `C:\Program Files\Tesseract-OCR`) to the `Path` environment variable.
* **Linux:** `sudo apt install tesseract-ocr tesseract-ocr-heb`

Check: `tesseract --list-langs` must show `heb`.

### 3. Poppler (PDF -> image)

* **Windows:** download the latest zip from
  https://github.com/oschwartz10612/poppler-windows/releases, extract it to a short
  English path (for example `C:\poppler`), and add its `Library\bin` folder to `Path`.
* **Linux:** `sudo apt install poppler-utils`

Check: `pdftoppm -v` must print a version.

No path is written in the code: Tesseract and Poppler are found through `Path`.
After changing `Path`, close and open the terminal (or VS Code) again.

### 4. A browser for the PDF output

The PDF is printed from the HTML page by Playwright (installed by `requirements.txt`).
It uses the first browser that works, in this order (`config/rules.py`,
`PDF_BROWSER_CHANNELS`):

1. Playwright's own Chromium: `python -m playwright install chromium`
2. Microsoft Edge (comes with every Windows)
3. Google Chrome

So on Windows nothing more is needed. If a network filter blocks the Chromium download
(error `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`), Edge is used. HTML output
(`--format html`) needs no browser at all.

---

## Tests

```bash
pytest
```

The tests run on the OCR text of the four samples, saved in `tests/fixtures/`
(from Linux and from Windows, because Tesseract reads them differently), so they do not
need Tesseract. The two tests that make a real PDF are skipped where no browser is
available. See `docs/testing.md`.

---

## How it works

A pipeline of five stations. Each station receives one thing and returns one thing:

```
PDF ──1 OCR──> raw text ──2 Classifier──> report type
    raw text ──3 Parser──> AttendanceReport ──4 Transformation──> new AttendanceReport
    new AttendanceReport ──5 Generation──> HTML / PDF
```

| Station | Code | Receives | Returns |
|---|---|---|---|
| 1. OCR | `parsing/ocr.py` | PDF path | raw text |
| 2. Classifier | `parsing/classifier.py` | raw text | `ReportType` |
| 3. Parser | `parsing/parser_factory.py`, `type_a_parser.py`, `type_b_parser.py` | raw text | `AttendanceReport` |
| 4. Transformation | `transformation/service.py`, `type_a_strategy.py`, `type_b_strategy.py` | `AttendanceReport` | new `AttendanceReport` |
| 5. Generation | `generation/html_renderer.py`, `pdf_renderer.py` | `AttendanceReport` | file |

After the parser, no station knows which PDF the report came from: they all work with
`AttendanceReport` (`domain/models.py`), a frozen dataclass whose rows are a tuple.
Times are stored as minutes, so there is no string arithmetic.

### Project structure

```
attendance_report/
├── main.py               entry point: builds the pieces and connects the stations
├── domain/               the shared language: models, errors, time arithmetic
├── config/               every number and setting (rules.py), classifier keywords
├── parsing/              stations 1-3: PDF -> AttendanceReport
├── transformation/       station 4: new times, recomputed totals, rule checks
├── generation/           station 5: AttendanceReport -> HTML / PDF
├── tests/                pytest, with the saved OCR text in tests/fixtures/
├── docs/                 decisions, OCR notes, architecture, testing
├── input_pdfs/           the sample reports
└── output/               the results (not in git)
```

### Design in one paragraph

The parser uses **Template Method**: `BaseParser.parse()` is written once, and each type
fills in how its rows and its summary are read. The transformation uses **Strategy**: one
strategy per type, chosen from a dictionary, so there is no `if` on the report type.
The generator has one renderer per **format** (HTML, PDF), and one layout per **type**
as data (`generation/layouts.py`). Adding a report type C means two new classes (parser,
strategy) and one line in each registry, without opening any existing logic.

### The rules (checked on every new report)

* Exit is after entry; times are inside a working day; a shift has a believable length.
* Row total = exit - entry - break.
* Type B: 100% + 125% + 150% + Shabbat = row total. On a regular day: up to 8 hours 100%,
  8 to 9 hours 125%, above 9 hours 150%. Shabbat hours go to the Shabbat column, holiday
  hours to 150%.
* Monthly totals = the sum of the rows; working days = rows with hours; pay = hourly
  rate x exact minutes.
* Same month, same days, and days without hours stay without hours.

If a rule is broken, the program stops with a list of every broken rule
(`transformation/validation.py`).

### Determinism

The same input always gives the same output: every row has its own random generator,
seeded by a fixed seed and the row's date (`random.Random(f"{seed}:{date}")`). So adding
or removing a row does not change the other rows. The new times keep the "roundness" of
the source: round times (8:30) stay round, minute-precise times (8:01) stay precise.

---

## Known limitations

* OCR errors in the source can survive into the output. Rows that could not be read are
  rebuilt (type A: from the date sequence; type B: from the day name), and every rebuilt
  row is reported as a warning.
* Values the OCR could not read are left empty, never invented: the hourly rate and the
  pay in type A, the bonus in type B.
* Every scan sits a little differently on the page, so the output has the structure of
  the source, not the exact position of each scan.

---

## Documentation

* `docs/decision_log.md`: every decision: the options, the choice, and why (Hebrew).
* `docs/ocr_notes.md`: what the OCR does to each sample, and how it is handled (Hebrew).
* `docs/architecture.md`: the stations and who may import whom.
* `docs/testing.md`: what is tested, and how.
* `docs/code_review_map.md`: where each item of the code review is in the code (Hebrew).
