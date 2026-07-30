"""Ingested timestamps are normalized to UTC so windowing/day-bucketing is
consistent across SQLite and Postgres."""
from __future__ import annotations

from datetime import UTC

from app.api.agents import _parse_ts


def test_offset_timestamp_normalized_to_utc():
    # 02:00 at +05:00 is 21:00 UTC the previous day.
    dt = _parse_ts("2026-07-30T02:00:00+05:00")
    assert dt.tzinfo == UTC
    assert dt.hour == 21
    assert dt.date().isoformat() == "2026-07-29"


def test_naive_timestamp_assumed_utc():
    dt = _parse_ts("2026-07-30T12:00:00")
    assert dt.tzinfo == UTC
    assert dt.hour == 12


def test_z_suffix_parsed():
    dt = _parse_ts("2026-07-30T08:30:00Z")
    assert dt.tzinfo == UTC
    assert dt.hour == 8


def test_none_and_garbage_default_to_now_utc():
    assert _parse_ts(None).tzinfo == UTC
    assert _parse_ts("not-a-date").tzinfo == UTC
