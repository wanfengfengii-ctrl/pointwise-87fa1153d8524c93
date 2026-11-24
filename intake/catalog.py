from dataclasses import dataclass

from intake.storage import IntakeStore
from issue.codec import decode_piece, encode_piece
from issue.envelope import FrozenPiece, PieceOrigin
from station.observations import require_number


@dataclass(frozen=True)
class ReceivedPiece:
    receipt_no: int
    piece: FrozenPiece

    @property
    def origin(self) -> PieceOrigin:
        return self.piece.origin


def accept_piece(store: IntakeStore, piece: FrozenPiece) -> ReceivedPiece:
    payload = encode_piece(piece)
    receipt_no = store.reconcile_delivery(piece.issue_id, payload)
    return ReceivedPiece(receipt_no, piece)


def load_received_piece(store: IntakeStore, receipt_no: int) -> ReceivedPiece | None:
    require_number(receipt_no, 'intake receipt number')
    payload = store.fetch_received(receipt_no)
    if payload is None:
        return None
    return ReceivedPiece(receipt_no, decode_piece(payload))
