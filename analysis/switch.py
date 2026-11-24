"""Exact two-piece switch review over a single B-bench cut."""

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Iterable, Sequence

from analysis.convex import ConvexRegion, normalize_regions
from analysis.lag_set import LagInterval
from analysis.objective import ScoreCell, build_score_cells
from analysis.overlap import build_overlap_cells
from issue.support import SupportSpan
from station.observations import RationalInput, parse_rational

Line = tuple[Fraction, Fraction, Fraction]
Point = tuple[Fraction, Fraction]
Affine = tuple[Fraction, Fraction, Fraction]

_ZERO = Fraction(0)
_ONE = Fraction(1)


@dataclass(frozen=True)
class SwitchRequest:
    a_receipt: int
    b_receipt: int
    cut: Fraction
    before_window: LagInterval
    after_window: LagInterval
    max_change: Fraction
    minimum_coverage: Fraction


@dataclass(frozen=True)
class SwitchDecision:
    regions: tuple[ConvexRegion, ...]
    minimum_mse: Fraction | None

    def contains(self, before_lag: RationalInput, after_lag: RationalInput) -> bool:
        point = (
            parse_rational(before_lag, 'before lag'),
            parse_rational(after_lag, 'after lag'),
        )
        if self.minimum_mse is None:
            return False
        return any(region.contains(point) for region in self.regions)


def split_before(spans: Iterable[SupportSpan], cut: Fraction) -> tuple[SupportSpan, ...]:
    pieces = []
    for span in spans:
        if span.start < cut:
            pieces.append(SupportSpan(span.start, min(span.end, cut), span.value))
    return tuple(pieces)


def split_after(spans: Iterable[SupportSpan], cut: Fraction) -> tuple[SupportSpan, ...]:
    pieces = []
    for span in spans:
        if span.end > cut:
            pieces.append(SupportSpan(max(span.start, cut), span.end, span.value))
    return tuple(pieces)


def _affine_terms(cell: ScoreCell, axis: int) -> tuple[Affine, Affine]:
    start, end = cell.window.start, cell.window.end
    if end == start:
        coverage = [_ZERO, _ZERO, cell.coverage_start]
        integral = [_ZERO, _ZERO, cell.integral_start]
    else:
        span = end - start
        coverage_slope = (cell.coverage_end - cell.coverage_start) / span
        integral_slope = (cell.integral_end - cell.integral_start) / span
        coverage = [_ZERO, _ZERO, cell.coverage_start - coverage_slope * start]
        integral = [_ZERO, _ZERO, cell.integral_start - integral_slope * start]
        coverage[axis] = coverage_slope
        integral[axis] = integral_slope
    return tuple(coverage), tuple(integral)


def _combine(*terms: Affine) -> Affine:
    return (
        sum((term[0] for term in terms), _ZERO),
        sum((term[1] for term in terms), _ZERO),
        sum((term[2] for term in terms), _ZERO),
    )


def _value(form: Affine, point: Point) -> Fraction:
    return form[0] * point[0] + form[1] * point[1] + form[2]


def _intersect(first: Line, second: Line) -> Point | None:
    a1, b1, c1 = first
    a2, b2, c2 = second
    determinant = a1 * b2 - a2 * b1
    if determinant == 0:
        return None
    return ((b1 * c2 - b2 * c1) / determinant, (a2 * c1 - a1 * c2) / determinant)


def _satisfies(point: Point, constraints: Sequence[Line]) -> bool:
    return all(_value(line, point) >= 0 for line in constraints)


def _vertices(constraints: Sequence[Line]) -> list[Point]:
    points = set()
    for index, first in enumerate(constraints):
        for second in constraints[index + 1:]:
            point = _intersect(first, second)
            if point is not None and _satisfies(point, constraints):
                points.add(point)
    return sorted(points)


def _build_constraints(
    before_cell: ScoreCell,
    after_cell: ScoreCell,
    coverage: Affine,
    max_change: Fraction,
    minimum_coverage: Fraction,
) -> list[Line]:
    x0, x1 = before_cell.window.start, before_cell.window.end
    y0, y1 = after_cell.window.start, after_cell.window.end
    return [
        (_ONE, _ZERO, -x0),
        (-_ONE, _ZERO, x1),
        (_ZERO, _ONE, -y0),
        (_ZERO, -_ONE, y1),
        (-_ONE, _ONE, _ZERO),
        (_ONE, -_ONE, max_change),
        (coverage[0], coverage[1], coverage[2] - minimum_coverage),
    ]


def _optimal_region(
    constraints: Sequence[Line],
    integral: Affine,
    coverage: Affine,
) -> tuple[Fraction, ConvexRegion] | None:
    corners = _vertices(constraints)
    if not corners:
        return None
    best = None
    for point in corners:
        ratio = _value(integral, point) / _value(coverage, point)
        if best is None or ratio < best:
            best = ratio
    level = _combine(integral, (-best * coverage[0], -best * coverage[1], -best * coverage[2]))
    if level == (_ZERO, _ZERO, _ZERO):
        return best, ConvexRegion(tuple(corners))
    optimal: set[Point] = {point for point in corners if _value(level, point) == 0}
    for line in constraints:
        point = _intersect(level, line)
        if point is not None and _satisfies(point, constraints):
            optimal.add(point)
    if not optimal:
        return None
    return best, ConvexRegion(tuple(optimal))


def solve_switch(
    a_support: tuple[SupportSpan, ...],
    b_support: tuple[SupportSpan, ...],
    cut: Fraction,
    before_window: LagInterval,
    after_window: LagInterval,
    max_change: Fraction,
    minimum_coverage: Fraction,
) -> SwitchDecision:
    if minimum_coverage <= 0:
        raise ValueError('minimum common coverage must be positive')
    if max_change < 0:
        raise ValueError('maximum switch change must not be negative')
    before_cells = build_score_cells(
        build_overlap_cells(a_support, split_before(b_support, cut), before_window)
    )
    after_cells = build_score_cells(
        build_overlap_cells(a_support, split_after(b_support, cut), after_window)
    )
    before_terms = [(cell,) + _affine_terms(cell, 0) for cell in before_cells]
    after_terms = [(cell,) + _affine_terms(cell, 1) for cell in after_cells]
    candidates: list[tuple[Fraction, ConvexRegion]] = []
    for before_cell, before_coverage, before_integral in before_terms:
        for after_cell, after_coverage, after_integral in after_terms:
            coverage = _combine(before_coverage, after_coverage)
            integral = _combine(before_integral, after_integral)
            constraints = _build_constraints(
                before_cell, after_cell, coverage, max_change, minimum_coverage,
            )
            optimum = _optimal_region(constraints, integral, coverage)
            if optimum is not None:
                candidates.append(optimum)
    if not candidates:
        return SwitchDecision((), None)
    best = min(ratio for ratio, _ in candidates)
    regions = normalize_regions(
        region for ratio, region in candidates if ratio == best
    )
    return SwitchDecision(regions, best)
