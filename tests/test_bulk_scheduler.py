from datetime import datetime
from zoneinfo import ZoneInfo

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.scheduling import distribute_targets, parse_times_list


def test_distribute_targets_three_slots():
    targets = list(range(10))
    start = datetime(2024, 1, 1, 18, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    times = parse_times_list(["18:00", "20:00", "22:00"])
    schedule = distribute_targets(targets, start, times_of_day=times, interval_days=1)
    assert len(schedule) == len(targets)
    assert schedule[0].hour == 18
    assert schedule[1].hour == 20
    assert schedule[2].hour == 22
    assert schedule[3].day == 2  # next day after filling slots
    assert schedule[-1] >= start
    assert all(dt.tzinfo is not None for dt in schedule)


def test_distribute_targets_skips_past_slots_same_day():
    targets = [1, 2]
    start = datetime(2024, 1, 1, 21, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    times = parse_times_list(["18:00", "20:00", "21:30"])
    schedule = distribute_targets(targets, start, times_of_day=times, interval_days=1)
    assert schedule[0].hour == 21 and schedule[0].minute == 30
    assert schedule[1].day == 2  # next available day
