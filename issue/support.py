from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from station.observations import Observation


@dataclass(frozen=True)
class SupportSpan:
    start: Fraction
    end: Fraction
    value: Fraction


def project_support(observations: Iterable[Observation]) -> tuple[SupportSpan, ...]:
    return tuple(
        SupportSpan(row.start, row.end, row.value)
        for row in observations
        if row.value is not None
    )


def validate_support(spans: tuple[SupportSpan, ...]) -> None:
    if not isinstance(spans, tuple):
        raise ValueError('frozen support must be an immutable sequence')
    previous_end = None
    for span in spans:
        if not isinstance(span, SupportSpan):
            raise ValueError('frozen support contains an invalid span')
        if not all(isinstance(field, Fraction) for field in (span.start, span.end, span.value)):
            raise ValueError('frozen support requires exact rational times and values')
        if span.start >= span.end:
            raise ValueError('frozen span start must precede its end')
        if previous_end is not None and span.start < previous_end:
            raise ValueError('frozen support must be sorted and disjoint')
        previous_end = span.end
