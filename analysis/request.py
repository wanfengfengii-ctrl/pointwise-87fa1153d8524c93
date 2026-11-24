from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from analysis.lag_set import LagInterval
from analysis.minima import ReviewDecision, solve_minima
from analysis.switch import SwitchDecision, SwitchRequest, solve_switch
from intake.selection import select_review_pair
from intake.storage import IntakeStore
from station.observations import RationalInput, parse_rational, require_number

if TYPE_CHECKING:
    from publication.storage import PublicationStore, ReportRecord


@dataclass(frozen=True)
class ReviewRequest:
    a_receipt: int
    b_receipt: int
    window: LagInterval
    minimum_coverage: Fraction


def validate_request(
    a_receipt: int,
    b_receipt: int,
    lower: RationalInput,
    upper: RationalInput,
    minimum_coverage: RationalInput,
) -> ReviewRequest:
    require_number(a_receipt, 'A intake receipt number')
    require_number(b_receipt, 'B intake receipt number')
    window = LagInterval(parse_rational(lower, 'lower lag'), parse_rational(upper, 'upper lag'))
    floor = parse_rational(minimum_coverage, 'minimum common coverage')
    if floor <= 0:
        raise ValueError('minimum common coverage must be positive')
    return ReviewRequest(a_receipt, b_receipt, window, floor)


def _parse_window(value, field: str) -> LagInterval:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f'{field} must give a lower and an upper bound')
    return LagInterval(
        parse_rational(value[0], f'{field} lower bound'),
        parse_rational(value[1], f'{field} upper bound'),
    )


def validate_switch_request(
    a_receipt: int,
    b_receipt: int,
    cut: RationalInput,
    before_window,
    after_window,
    max_change: RationalInput,
    minimum_coverage: RationalInput,
) -> SwitchRequest:
    require_number(a_receipt, 'A intake receipt number')
    require_number(b_receipt, 'B intake receipt number')
    before = _parse_window(before_window, 'before window')
    after = _parse_window(after_window, 'after window')
    change = parse_rational(max_change, 'maximum switch change')
    if change < 0:
        raise ValueError('maximum switch change must not be negative')
    floor = parse_rational(minimum_coverage, 'minimum common coverage')
    if floor <= 0:
        raise ValueError('minimum common coverage must be positive')
    return SwitchRequest(
        a_receipt,
        b_receipt,
        parse_rational(cut, 'switching cut'),
        before,
        after,
        change,
        floor,
    )


def review(
    intake: IntakeStore,
    publication: PublicationStore,
    a_receipt: int,
    b_receipt: int,
    lower: RationalInput,
    upper: RationalInput,
    minimum_coverage: RationalInput,
) -> ReportRecord:
    from publication.finalize import finalize_report

    request = validate_request(a_receipt, b_receipt, lower, upper, minimum_coverage)
    pair = select_review_pair(intake, request.a_receipt, request.b_receipt)
    decision = solve_minima(
        pair.a.piece.support, pair.b.piece.support, request.window, request.minimum_coverage,
    )
    return finalize_report(publication, request, decision, pair)


def review_switch(
    intake: IntakeStore,
    publication: PublicationStore,
    a_receipt: int,
    b_receipt: int,
    cut: RationalInput,
    before_window,
    after_window,
    max_change: RationalInput,
    minimum_coverage: RationalInput,
) -> ReportRecord:
    from publication.finalize import finalize_report

    request = validate_switch_request(
        a_receipt, b_receipt, cut, before_window, after_window, max_change, minimum_coverage,
    )
    pair = select_review_pair(intake, request.a_receipt, request.b_receipt)
    decision = solve_switch(
        pair.a.piece.support,
        pair.b.piece.support,
        request.cut,
        request.before_window,
        request.after_window,
        request.max_change,
        request.minimum_coverage,
    )
    return finalize_report(publication, request, decision, pair)
