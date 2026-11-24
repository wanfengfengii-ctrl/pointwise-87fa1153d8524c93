from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from station.observations import parse_rational


@dataclass(frozen=True, order=True)
class LagInterval:
    start: Fraction
    end: Fraction

    def __post_init__(self) -> None:
        start = parse_rational(self.start, 'lag interval start')
        end = parse_rational(self.end, 'lag interval end')
        if start > end:
            raise ValueError('lag interval start must not exceed its end')
        object.__setattr__(self, 'start', start)
        object.__setattr__(self, 'end', end)


def merge_lag_intervals(intervals: Iterable[LagInterval]) -> tuple[LagInterval, ...]:
    merged = []
    for interval in sorted(intervals):
        if merged and interval.start <= merged[-1].end:
            previous = merged[-1]
            merged[-1] = LagInterval(previous.start, max(previous.end, interval.end))
        else:
            merged.append(interval)
    return tuple(merged)
