from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise, product
from typing import Iterator

from analysis.lag_set import LagInterval
from issue.support import SupportSpan


@dataclass(frozen=True)
class OverlapTerm:
    start_length: Fraction
    end_length: Fraction
    a_value: Fraction
    b_value: Fraction


@dataclass(frozen=True)
class OverlapCell:
    window: LagInterval
    terms: tuple[OverlapTerm, ...]


def intersect_support(a: SupportSpan, b: SupportSpan, lag: Fraction) -> Fraction:
    start = max(a.start, b.start + lag)
    end = min(a.end, b.end + lag)
    return max(Fraction(0), end - start)


def _lag_breakpoints(
    a_support: tuple[SupportSpan, ...],
    b_support: tuple[SupportSpan, ...],
    window: LagInterval,
) -> list[Fraction]:
    a_endpoints = {endpoint for span in a_support for endpoint in (span.start, span.end)}
    b_endpoints = {endpoint for span in b_support for endpoint in (span.start, span.end)}
    breakpoints = {window.start, window.end}
    for a_end, b_end in product(a_endpoints, b_endpoints):
        lag = a_end - b_end
        if window.start < lag < window.end:
            breakpoints.add(lag)
    return sorted(breakpoints)


def build_overlap_cells(
    a_support: tuple[SupportSpan, ...],
    b_support: tuple[SupportSpan, ...],
    window: LagInterval,
) -> Iterator[OverlapCell]:
    breakpoints = _lag_breakpoints(a_support, b_support, window)
    edges = pairwise(breakpoints) if len(breakpoints) > 1 else iter([(window.start, window.end)])
    for start, end in edges:
        terms = []
        for a, b in product(a_support, b_support):
            start_length = intersect_support(a, b, start)
            end_length = intersect_support(a, b, end)
            # Each intersection length is affine between adjacent endpoint differences.
            if start_length or end_length:
                terms.append(OverlapTerm(start_length, end_length, a.value, b.value))
        yield OverlapCell(LagInterval(start, end), tuple(terms))
