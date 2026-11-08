"""Tests for domain/time_math.py."""
from decimal import Decimal

import pytest

from domain.exceptions import TimeConversionError
from domain.time_math import (
    MINUTES_PER_DAY,
    clock_to_minutes,
    decimal_hours_to_minutes,
    minutes_to_clock_text,
    minutes_to_decimal_hours,
    common_time_step,
    times_on_grid,
    worked_minutes,
)


class TestClock:
    def test_clock_to_minutes(self):
        assert clock_to_minutes(8, 30) == 510

    def test_midnight_is_zero(self):
        assert clock_to_minutes(0, 0) == 0

    def test_last_minute_of_the_day(self):
        assert clock_to_minutes(23, 59) == MINUTES_PER_DAY - 1

    @pytest.mark.parametrize("hour, minute", [(24, 0), (-1, 0), (8, 60), (8, -1)])
    def test_invalid_time_is_rejected(self, hour, minute):
        with pytest.raises(TimeConversionError):
            clock_to_minutes(hour, minute)

    def test_minutes_to_clock_text_pads_with_zeros(self):
        assert minutes_to_clock_text(510) == "08:30"
        assert minutes_to_clock_text(0) == "00:00"

    @pytest.mark.parametrize("minutes", [-1, MINUTES_PER_DAY])
    def test_minutes_outside_a_day_are_rejected(self, minutes):
        with pytest.raises(TimeConversionError):
            minutes_to_clock_text(minutes)

    @pytest.mark.parametrize("hour, minute", [(0, 0), (8, 30), (15, 0), (23, 59)])
    def test_round_trip(self, hour, minute):
        text = minutes_to_clock_text(clock_to_minutes(hour, minute))
        assert text == f"{hour:02d}:{minute:02d}"


class TestDecimalHours:
    def test_six_and_a_half_hours(self):
        assert decimal_hours_to_minutes(Decimal("6.50")) == 390
        assert minutes_to_decimal_hours(390) == Decimal("6.50")

    def test_values_from_the_sample_reports(self):
        assert decimal_hours_to_minutes(Decimal("3.50")) == 210
        assert decimal_hours_to_minutes(Decimal("143.00")) == 8580

    def test_not_a_round_number_of_hours(self):
        assert minutes_to_decimal_hours(380) == Decimal("6.33")

    def test_decimal_hours_are_rounded_to_a_whole_minute(self):
        assert decimal_hours_to_minutes(Decimal("6.33")) == 380

    def test_zero(self):
        assert minutes_to_decimal_hours(0) == Decimal("0.00")


class TestWorkedMinutes:
    def test_without_break(self):
        assert worked_minutes(510, 720) == 210

    def test_break_is_taken_off(self):
        # type B: 08:00-15:00 with 00:30 break = 6.50 hours
        assert worked_minutes(480, 900, 30) == 390


class TestTimeGrid:
    def test_round_source_has_a_round_step(self):
        assert common_time_step([510, 720, 510, 720], (30, 15, 5, 1), 0.9) == 30  # 8:30, 12:00

    def test_minute_precise_source_has_step_one(self):
        assert common_time_step([481, 665, 483, 663], (30, 15, 5, 1), 0.9) == 1  # 8:01, 11:05 ...

    def test_one_ocr_error_does_not_cancel_the_step(self):
        times = [510, 720] * 10 + [530]  # 20 round times and one 8:50 that OCR misread
        assert common_time_step(times, (30, 15, 10, 5, 1), 0.9) == 30

    def test_no_times_means_step_one(self):
        assert common_time_step([], (30, 15, 1), 0.9) == 1

    def test_choices_on_a_quarter_hour_grid(self):
        assert times_on_grid(510, 15, 15) == [495, 510, 525]  # 8:15, 8:30, 8:45

    def test_a_time_off_the_grid_moves_onto_it(self):
        assert times_on_grid(530, 15, 15) == [525, 540]  # 8:50 -> 8:45 or 9:00

    def test_step_one_is_every_minute(self):
        assert times_on_grid(510, 2, 1) == [508, 509, 510, 511, 512]
