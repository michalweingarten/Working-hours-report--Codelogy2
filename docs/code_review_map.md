# מפת הקוד ריוויו: איפה כל תחנת בדיקה נמצאת בקוד

המסמך עוזר למלא את קובץ הקוד ריוויו המודרך. לכל תחנת בדיקה כתוב איפה היא בקוד, ומה עוד פתוח.
את הסימון עצמו (✓ / ◐ / ✗) עושים בכנות, אחרי שבודקים בקוד.

## 1. התמונה הגדולה
| תחנת בדיקה | איפה |
|---|---|
| הפלט הוא וריאציה הגיונית | `transformation/service.py` + `transformation/validation.py`, ופלט ב-`output/` |
| חמש התחנות | `parsing/ocr.py`, `parsing/classifier.py`, `parsing/parser_factory.py` + `type_a_parser.py`, `transformation/service.py`, `generation/` |
| כל תחנה מקבלת פרמטר ומחזירה תוצאה | `main.process_pdf`: ‏str → ReportType → AttendanceReport → AttendanceReport → Path |
| אחרי הפרסר אף קוד לא חוזר לטקסט | הטרנספורמציה והגנרוט מקבלים רק `AttendanceReport` |

## 2. מפת הפרויקט
| תחנת בדיקה | איפה |
|---|---|
| תיקייה לכל שלב | `domain/`, `config/`, `parsing/`, `transformation/`, `generation/`, `tests/` |
| main קצר, כמו תוכן עניינים | `main.py`: ‏`process_pdf` הוא חמש תחנות, השאר הוא argparse |
| `if __name__ == "__main__"` | סוף `main.py`. טסטים מייבאים ממנו בלי להריץ OCR |
| domain לא מייבא מהפרויקט, generation לא מייבא מ-parsing | נבדק בטסט `test_generation_does_not_import_other_stations` |
| אין נתיבים של המחשב | Tesseract ו-Poppler נמצאים דרך Path, וההסבר ב-README |
| בלי `sys.path.append` | `pytest.ini`: ‏`pythonpath = .` |

## 3. המודל
| תחנת בדיקה | איפה |
|---|---|
| שעות כדקות ולא כמחרוזות | `domain/models.py`, החלטה ביומן (שלב 2) |
| frozen ו-tuple | כל המחלקות ב-`domain/models.py` |
| מודל אחד לכל התחנות | `AttendanceReport` |
| שדות B אופציונליים | `AttendanceRow`: ‏`break_minutes`, `pay_100_minutes` וכו', `None` בסוג A |
| הסוג מוגדר במקום אחד | `ReportType` (Enum) ב-`domain/models.py` |
| שבת וחג במודל בלי שעות, ומופיעים בפלט | `RowKind.SHABBAT`, ושורות חג בלי שעות |

## 4. OOP
| תחנת בדיקה | איפה |
|---|---|
| `@abstractmethod` | `TextExtractor` ‏(`parsing/ocr.py`), `BaseTransformationStrategy`, `BaseRenderer` |
| אותה קריאה על כמה מחלקות | `main.process_pdf`: ‏`RENDERERS[f].render(...)` עובד על HtmlRenderer ועל PdfRenderer |
| מילון במקום if/elif | `PARSERS`, `TRANSFORM_RULES`, `LAYOUTS`, `RENDERERS`, `CELL_FORMATTERS`, `REPORT_KEYWORDS` |

## 5. התחנות
| תחנת בדיקה | איפה / סטטוס |
|---|---|
| רק קובץ אחד מייבא pytesseract | `parsing/ocr.py` |
| כל העמודים נקראים | `TesseractTextExtractor.extract`: לולאה על כל העמודים |
| ניקוי, וכל כלל מפלט אמיתי | `parsing/text_tools.py`, ‏`docs/ocr_notes.md` |
| טקסט הדוגמאות שמור | `tests/fixtures/` |
| זיהוי לפי כמה ראיות | `parsing/classifier.py` + `config/report_keywords.py` |
| קובץ שאינו דו"ח מקבל שגיאה | `ClassificationError` |
| ארבעת הקבצים מזוהים, עם טסט | `tests/test_classifier.py` |
| BaseParser עם parse() משותף | `parsing/base_parser.py`: ‏`parse()` כתובה פעם אחת. `TypeAParser` ו-`TypeBParser` ממלאים רק `_parse_rows` ו-`_parse_summary`. טסט: `test_both_parsers_share_the_parse_flow` |
| אין קוד מועתק בין פרסרים | חודש, עוגני תאריכים וניקוי: ב-`BaseParser` וב-`parsing/text_tools.py` |
| שעות לפי מיקום בעמודה | סוג B: כניסה, יציאה, הפסקה לפי הסדר (`TypeBParser._read`), וטסט `test_break_is_read_by_position_not_as_the_smallest_time`. סוג A: המוקדמת והמאוחרת, בכוונה (החלטה 40) |
| Factory | `parsing/parser_factory.py`: ‏`PARSERS` |
| שורה שלא נקראה מדווחת | `logging.warning` בפרסר, ושחזור לפי רצף |
| הפרסר מחזיר AttendanceReport | `TypeAParser.parse` |
| אסטרטגיה לכל סוג, מילון בשירות | `transformation/service.py`, `type_a_strategy.py`, `type_b_strategy.py` |
| דו"ח חדש, המקור לא משתנה | `replace()`, frozen, וטסט `test_original_is_not_changed` |
| שתי הרצות זהות, seed מהתאריך | `TransformationService._rng_for`: ‏`Random(f"{seed}:{date}")` |
| חישוב מחדש של הסיכום | `build_summary` בשתי האסטרטגיות. ב-B גם 100/125/150/שבת והפסקות |
| בדיקה אחת שרצה על כל שורה | `validation.row_violations` |
| מספרים מ-config | `config/rules.py`: ‏`TRANSFORM_RULES` |
| שבת וחג בלי שעות | `transform_row`: ‏`if not row.has_hours: return row` |
| הגנרוט מקבל רק AttendanceReport | `generation/` |
| מחלקה לכל פורמט | `HtmlRenderer`, `PdfRenderer` יורשים מ-`BaseRenderer` |
| ההבדל בין הסוגים כנתונים | `generation/layouts.py`: ‏`LAYOUTS` (רשימת בלוקים לכל סוג), ו-`Column.field`. טסט: `test_renderer_has_no_if_on_the_report_type` |
| הגנרוט לא מחשב סכומים | `html_renderer.py` רק מעצב את מה שקיבל |
| עברית ו-RTL | `dir="rtl"`, ‏Arial / Liberation Sans |
| מקור ופלט זה לצד זה | נבדק בשלב 6. הפערים ביומן (34) |
| המקור לא נדרס | הפלט ב-`output/<שם>_variant.*` |
| main בלי לוגיקה של תחנה | `main.process_pdf` |
| אובייקטים נוצרים ב-main | `TRANSFORMER`, `RENDERERS` ב-`main.py` |
| שגיאה בקובץ = הודעה ברורה | `main.main`: ‏`Failed: ...` וממשיך לקובץ הבא |
| בונוס argparse | `main.parse_args`: ‏`--help`, ‏`-o`, ‏`--format`, ‏`-q` |

## 6. מה שחוצה את הפרויקט
| תחנת בדיקה | איפה / סטטוס |
|---|---|
| כל המספרים ב-config | `config/rules.py` |
| היררכיית שגיאות, בלי except ריק | `domain/exceptions.py` |
| טסט ל-Classifier, Parser, Transformation | `tests/` |
| כל אינווריאנט נבדק | `tests/test_validation.py` |
| README | `README.md`: מה הפרויקט עושה, התקנה (כולל Tesseract, עברית, Poppler ו-Path), הרצה, טסטים, מבנה. לבדוק: חברה מריצה לפיו בלי לשאול |
| יומן החלטות מלא | `docs/decision_log.md` |
| בונוס Docker | לא נעשה. החלטה 50 ביומן |

## 7. מבחן הגמישות: מה פותחים כדי להוסיף סוג C
כל השורות הבאות הן הוספה למילון או לרשימה. אף לוגיקה קיימת לא נפתחת.
1. `domain/models.py`: ‏`TYPE_C` ב-`ReportType`
2. `config/report_keywords.py`: מילות המפתח
3. `parsing/type_c_parser.py` (חדש) ושורה ב-`PARSERS`
4. `transformation/type_c_strategy.py` (חדש) ושורה ב-`TRANSFORMER` ב-`main.py`
5. `config/rules.py`: שורה ב-`TRANSFORM_RULES`
6. `generation/layouts.py`: שורה ב-`LAYOUTS` (ושדות חדשים ב-`CELL_FORMATTERS`, אם יש)

פורמט פלט חדש: מחלקה חדשה ב-`generation/` ושורה ב-`RENDERERS`.
כלל חדש (טווח הזזה): ערך אחד ב-`TRANSFORM_RULES`.

## 9. שאלה 10 בראיון: איפה ה-AI טעה, ואיך זה התגלה
- **seed אחד לכל הדו"ח** (`Random(42)` פעם אחת). דטרמיניסטי, אבל הוספה או הסרה של שורה הזיזה את כל השורות שאחריה. התגלה בקוד ריוויו, ותוקן ל-seed לכל שורה לפי התאריך. יש טסט: `test_rows_do_not_affect_each_other`.
- **`except Exception`** בפונקציית עזר של הבדיקות. התגלה בקוד ריוויו, והוחלף ב-`TimeConversionError`.
- **"לשורה משוחזרת אין מיקום בתמונה"**: טענה שגויה בדיון על שלב 6. השורה קיימת בסריקה, רק ה-OCR לא קרא אותה. התגלה כשבדקנו את הסריקה בפועל.
- **צפי של 24 ימים ב-n_r_5_n** נבדק רק על פלט OCR של Linux. ב-Windows יצא 23, והתגלה שורה שיש בה רק `|`. תוקן (החלטה 26), ונוסף טסט על הפלט של Windows.
