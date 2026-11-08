"""Tests for parsing/text_tools.py."""
from parsing.text_tools import (
    DateParts,
    clean_text,
    find_clock_times,
    find_dates,
    find_hour_amounts,
    find_numbers,
    find_weekday,
    flatten_text,
)

RIGHT_TO_LEFT_MARK = chr(0x200F)
LEFT_TO_RIGHT_MARK = chr(0x200E)
GERESHAYIM = chr(0x5F4)
CURLY_QUOTE = chr(0x201D)


class TestCleanText:
    def test_removes_direction_marks(self):
        noisy = f"{RIGHT_TO_LEFT_MARK}שבת{LEFT_TO_RIGHT_MARK}"
        assert clean_text(noisy) == "שבת"

    def test_removes_every_kind_of_quote(self):
        for quote in ('"', GERESHAYIM, CURLY_QUOTE):
            assert clean_text(f"סה{quote}כ") == "סהכ"

    def test_keeps_line_breaks(self):
        assert clean_text("a\nb") == "a\nb"

    def test_squeezes_repeated_spaces_inside_a_line(self):
        assert clean_text("a   b \t c") == "a b c"

    def test_empty_text(self):
        assert clean_text("") == ""


class TestFlattenText:
    def test_puts_everything_on_one_line(self):
        assert flatten_text("a\n\n  b\nc") == "a b c"

    def test_word_split_by_a_direction_mark_is_joined_again(self):
        assert flatten_text(f"הפ{RIGHT_TO_LEFT_MARK}סקה") == "הפסקה"


class TestFindDates:
    def test_a_normal_date(self):
        assert find_dates("| 1/9/22 | חמישי |") == [DateParts(day=1, month=9, year=2022)]

    def test_a_broken_date_is_not_a_date(self):
        assert find_dates("17191229 | 44/23") == []


class TestFindNumbers:
    def test_times_and_total_with_their_marks(self):
        numbers = find_numbers("| 1/9/22 | 8:30 | 12:00 | 3.50 |")
        assert numbers.clock_times == (510, 720)
        assert numbers.hour_amounts == (210,)

    def test_colon_lost(self):
        assert find_numbers("1200").clock_times == (720,)

    def test_colon_read_as_zero(self):
        assert find_numbers("12000").clock_times == (720,)

    def test_three_digits_with_high_first_digit_is_a_time(self):
        assert find_numbers("803").clock_times == (483,)

    def test_three_digits_with_low_first_digit_is_hours(self):
        assert find_numbers("350").hour_amounts == (210,)

    def test_impossible_time_is_skipped(self):
        assert find_numbers("10:67").clock_times == ()

    def test_digits_of_a_date_are_not_times(self):
        assert find_numbers("| 12/9/22 |").clock_times == ()


class TestTypeBReading:
    LINE = "2 יום ראשון | גליליון | 08:00 15:00 00:30 6.50 650 0.00 0.00 000"

    def test_four_digit_year(self):
        assert find_dates("07/10/2022 גליליון") == [DateParts(day=7, month=10, year=2022)]

    def test_times_in_column_order(self):
        assert find_clock_times(self.LINE) == [480, 900, 30]  # entry, exit, break

    def test_amounts_in_column_order_with_lost_dots(self):
        assert find_hour_amounts(self.LINE) == [390, 390, 0, 0, 0]

    def test_noise_before_the_times_is_not_an_amount(self):
        line = "08/10/2022 ₪004 גליליון | 08:00 15:00 00:30 6.50 0.00 0.00 0.00 6.50"
        assert find_hour_amounts(line) == [390, 0, 0, 0, 390]

    def test_amounts_before_the_times_of_a_reversed_line(self):
        line = "0.00 0.00 0.00 7.50 7.50 00:30 16:00 08:00 גונן 3"
        assert find_hour_amounts(line, side="before") == [0, 0, 0, 450, 450]
        assert find_hour_amounts(line, side="after") == []

    def test_day_name(self):
        assert find_weekday(self.LINE) == 6  # Sunday

    def test_day_name_as_ocr_writes_it(self):
        assert find_weekday("3 יום ‘wow גונן 08:00") == 1  # Tuesday
        assert find_weekday("nw or 20/02/2023 גונן") == 0  # Monday

    def test_unknown_garble_is_not_guessed(self):
        assert find_weekday("2 יום ‘ww גליליון") is None
