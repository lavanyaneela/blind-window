"""The clock is injected and monotone; nothing here sleeps."""

import pytest

from blind_window.clock import ClockError, SimClock


def test_a_new_clock_starts_at_day_zero():
    assert SimClock().now() == 0.0


def test_advancing_to_a_later_day_moves_now():
    c = SimClock()
    c.advance_to(3.5)
    assert c.now() == 3.5


def test_advancing_by_a_span_adds_to_now():
    c = SimClock(day=2.0)
    c.advance_by(1.25)
    assert c.now() == 3.25


def test_the_clock_refuses_to_move_backwards():
    c = SimClock(day=5.0)
    with pytest.raises(ClockError):
        c.advance_to(4.0)


def test_the_clock_refuses_a_negative_span():
    with pytest.raises(ClockError):
        SimClock().advance_by(-1.0)


def test_advancing_to_the_same_day_is_allowed():
    c = SimClock(day=5.0)
    assert c.advance_to(5.0) == 5.0
