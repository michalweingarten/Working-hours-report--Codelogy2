# Testing

```bash
pytest                    # everything
pytest tests/test_parsers.py
pytest --durations=5      # the slowest tests
```

## Test data

`tests/fixtures/` holds the raw OCR text of the four samples, from Linux and from Windows
(Tesseract reads the same scan differently on each). The tests run on this text, so they
need neither Tesseract nor the PDFs. Every `n_r_*` file is type A, every `a_r_*` file is type B,
and a new sample is a new file: no test code changes.

## What each file checks

| File | What |
|---|---|
| `test_text_tools.py` | cleaning, and finding dates, times, amounts and day names in noisy lines |
| `test_classifier.py` | every sample gets the right type; weak or equal evidence is an error; one lost keyword does not matter |
| `test_parsers.py` | month, one row per day (A), dates (B), Shabbat and holidays, columns read by position, rebuilt rows, the shared `BaseParser` flow |
| `test_models.py` | the models are frozen; `replace()` builds a new object and keeps the original; type B fields are empty in type A |
| `test_time_math.py` | clock and decimal-hours conversions, the time grid |
| `test_transformation.py` | the original is not changed; same seed, same output; rows do not affect each other; totals, days and pay computed again; type B split and break |
| `test_validation.py` | one test per rule, the real numbers of the sources, all violations listed together |
| `test_generation.py` | right to left, Hebrew font, the layout of each type, no `if` on the type, one renderer per format, the PDF |
| `test_pipeline.py` | every sample through every station; the command line: `--help`, output folder, a bad file does not stop the others |

## Tests that need a browser

`test_pdf_is_made` prints a real PDF. Where no browser is available it is skipped, not
failed. On some Windows machines a browser starts slowly, so these two tests can take
about 20 seconds each.
