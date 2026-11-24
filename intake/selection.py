from dataclasses import dataclass

from intake.catalog import ReceivedPiece, load_received_piece
from intake.storage import IntakeStore


@dataclass(frozen=True)
class ReviewPair:
    a: ReceivedPiece
    b: ReceivedPiece


def select_review_pair(store: IntakeStore, a_receipt: int, b_receipt: int) -> ReviewPair:
    a = load_received_piece(store, a_receipt)
    b = load_received_piece(store, b_receipt)
    if a is None or b is None:
        unknown = a_receipt if a is None else b_receipt
        raise LookupError(f'unknown intake receipt {unknown}')
    if a.origin.role != 'A' or b.origin.role != 'B':
        raise ValueError('review requires the A receipt followed by the B receipt')
    if a.origin.batch_id != b.origin.batch_id:
        raise ValueError('review requires both receipts to belong to the same batch')
    if a.origin.bench_id == b.origin.bench_id:
        raise ValueError('review requires two distinct benches')
    if a.origin.unit != b.origin.unit:
        raise ValueError('review requires matching reading units')
    return ReviewPair(a, b)
