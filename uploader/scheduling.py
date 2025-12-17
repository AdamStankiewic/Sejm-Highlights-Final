from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Iterable, List
from zoneinfo import ZoneInfo


def parse_times_list(times: Iterable[str]) -> List[time]:
    parsed: list[time] = []
    for raw in times:
        item = raw.strip()
        if not item:
            continue
        try:
            hour, minute = item.split(":", 1)
            parsed.append(time(int(hour), int(minute)))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid time format: {item}") from exc
    if not parsed:
        raise ValueError("At least one time slot is required")
    return parsed


def distribute_targets(
    targets: list,
    start_dt: datetime,
    *,
    times_of_day: List[time],
    interval_days: int = 1,
    tz: str = "Europe/Warsaw",
) -> List[datetime]:
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=ZoneInfo(tz))
    tzinfo = start_dt.tzinfo
    if interval_days < 1:
        raise ValueError("interval_days must be >= 1")
    if not times_of_day:
        raise ValueError("times_of_day must not be empty")
    ordered_times = sorted(times_of_day)
    schedule: list[datetime] = []
    day = start_dt.date()
    target_iter = iter(targets)

    while len(schedule) < len(targets):
        for slot_time in ordered_times:
            candidate = datetime.combine(day, slot_time, tzinfo=tzinfo)
            if candidate < start_dt:
                continue
            schedule.append(candidate)
            if len(schedule) >= len(targets):
                break
        day = day + timedelta(days=interval_days)
    return schedule
