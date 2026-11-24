from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable


RationalInput = Fraction | int | str
ObservationInput = tuple[RationalInput, RationalInput, RationalInput | None]


def parse_rational(value: RationalInput, field: str) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if type(value) in (int, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f'{field} must be an exact rational number') from exc
    raise ValueError(f'{field} must be an exact rational number')


def require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or '\x00' in value:
        raise ValueError(f'{field} must be nonempty text without surrounding whitespace')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError(f'{field} must be valid Unicode text') from exc
    return value


def require_number(value: int, field: str) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError(f'{field} must be a positive SQLite integer')
    return value


@dataclass(frozen=True)
class Observation:
    start: Fraction
    end: Fraction
    value: Fraction | None


def normalize_observations(
    rows: Iterable[ObservationInput | Observation],
) -> tuple[Observation, ...]:
    try:
        source = iter(rows)
    except TypeError as exc:
        raise ValueError('observations must be an iterable of rows') from exc

    observations = []
    for number, row in enumerate(source, start=1):
        if isinstance(row, Observation):
            start, end, value = row.start, row.end, row.value
        elif isinstance(row, (tuple, list)) and len(row) == 3:
            start, end, value = row
        else:
            raise ValueError(f'observation {number} must have start, end and value')
        start = parse_rational(start, f'observation {number} start')
        end = parse_rational(end, f'observation {number} end')
        reading = None if value is None else parse_rational(value, f'observation {number} value')
        if start >= end:
            raise ValueError(f'observation {number} start must precede its end')
        observations.append(Observation(start, end, reading))

    observations.sort(key=lambda observation: observation.start)
    for left, right in zip(observations, observations[1:]):
        if right.start < left.end:
            raise ValueError(f'observation at {right.start} overlaps the preceding observation')
    return tuple(observations)
