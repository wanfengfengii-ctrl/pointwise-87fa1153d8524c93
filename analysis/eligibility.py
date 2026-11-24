from fractions import Fraction

from analysis.lag_set import LagInterval
from analysis.objective import ScoreCell


def clip_to_coverage(cell: ScoreCell, minimum_coverage: Fraction) -> LagInterval | None:
    left, right = cell.window.start, cell.window.end
    coverage_left = cell.coverage_at(left)
    coverage_right = cell.coverage_at(right)
    left_qualifies = coverage_left >= minimum_coverage
    right_qualifies = coverage_right >= minimum_coverage
    if left_qualifies and right_qualifies:
        return cell.window
    if not left_qualifies and not right_qualifies:
        return None
    fraction = (minimum_coverage - coverage_left) / (coverage_right - coverage_left)
    boundary = left + fraction * (right - left)
    if left_qualifies:
        return LagInterval(left, boundary)
    return LagInterval(boundary, right)
