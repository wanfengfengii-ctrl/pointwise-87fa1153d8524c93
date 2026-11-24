from dataclasses import dataclass

from intake.selection import ReviewPair
from issue.envelope import PieceOrigin


@dataclass(frozen=True)
class ParentReference:
    receipt_no: int
    issue_id: str
    origin: PieceOrigin


def snapshot_parents(pair: ReviewPair) -> tuple[ParentReference, ParentReference]:
    return (
        ParentReference(pair.a.receipt_no, pair.a.piece.issue_id, pair.a.origin),
        ParentReference(pair.b.receipt_no, pair.b.piece.issue_id, pair.b.origin),
    )
