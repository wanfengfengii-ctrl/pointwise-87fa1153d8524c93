from intake.catalog import ReceivedPiece, accept_piece
from intake.storage import IntakeStore
from issue.codec import decode_piece
from issue.envelope import FrozenPiece


def receive_piece(store: IntakeStore, piece_or_bytes: FrozenPiece | bytes) -> ReceivedPiece:
    piece = decode_piece(piece_or_bytes) if isinstance(piece_or_bytes, bytes) else piece_or_bytes
    return accept_piece(store, piece)
