from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from analysis.lag_set import LagInterval
from analysis.minima import solve_minima
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
