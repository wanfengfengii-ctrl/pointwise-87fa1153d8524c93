from dataclasses import dataclass
from fractions import Fraction

from analysis.eligibility import clip_to_coverage
from analysis.lag_set import LagInterval, merge_lag_intervals
from analysis.objective import build_score_cells
from analysis.overlap import build_overlap_cells
from issue.support import SupportSpan


@dataclass(frozen=True)
class ReviewDecision:
    intervals: tuple[LagInterval, ...]
    minimum_mse: Fraction | None


def solve_minima(
    a_support: tuple[SupportSpan, ...],
    b_support: tuple[SupportSpan, ...],
    window: LagInterval,
    minimum_coverage: Fraction,
) -> ReviewDecision:
    if minimum_coverage <= 0:
        raise ValueError('minimum common coverage must be positive')
    best = None
    intervals = []
    overlaps = build_overlap_cells(a_support, b_support, window)
    for cell in build_score_cells(overlaps):
        eligible = clip_to_coverage(cell, minimum_coverage)
        if eligible is None:
            continue
        start, end = eligible.start, eligible.end
        left_score = cell.mean_square_at(start)
        right_score = cell.mean_square_at(end)
        # An affine quotient with positive denominator is monotone or constant.
        if left_score < right_score:
            candidate = LagInterval(start, start)
        elif right_score < left_score:
            candidate = LagInterval(end, end)
        else:
            candidate = eligible
        score = min(left_score, right_score)
        if best is None or score < best:
            best = score
            intervals = [candidate]
        elif score == best:
            intervals.append(candidate)
    return ReviewDecision(merge_lag_intervals(intervals), best)
