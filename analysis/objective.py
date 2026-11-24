from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Iterator

from analysis.lag_set import LagInterval
from analysis.overlap import OverlapCell


@dataclass(frozen=True)
class ScoreCell:
    window: LagInterval
    coverage_start: Fraction
    coverage_end: Fraction
    integral_start: Fraction
    integral_end: Fraction

    def _position(self, lag: Fraction) -> Fraction:
        if not self.window.start <= lag <= self.window.end:
            raise ValueError('lag is outside the score cell')
        if self.window.start == self.window.end:
            return Fraction(0)
        return (lag - self.window.start) / (self.window.end - self.window.start)

    def coverage_at(self, lag: Fraction) -> Fraction:
        position = self._position(lag)
        return self.coverage_start + position * (self.coverage_end - self.coverage_start)

    def mean_square_at(self, lag: Fraction) -> Fraction:
        position = self._position(lag)
        coverage = self.coverage_start + position * (self.coverage_end - self.coverage_start)
        if coverage <= 0:
            raise ValueError('mean square requires positive common coverage')
        integral = self.integral_start + position * (self.integral_end - self.integral_start)
        return integral / coverage


def build_score_cells(overlaps: Iterable[OverlapCell]) -> Iterator[ScoreCell]:
    for cell in overlaps:
        coverage_start = coverage_end = Fraction(0)
        integral_start = integral_end = Fraction(0)
        for term in cell.terms:
            squared_difference = (term.a_value - term.b_value) ** 2
            coverage_start += term.start_length
            coverage_end += term.end_length
            integral_start += term.start_length * squared_difference
            integral_end += term.end_length * squared_difference
        yield ScoreCell(cell.window, coverage_start, coverage_end, integral_start, integral_end)
