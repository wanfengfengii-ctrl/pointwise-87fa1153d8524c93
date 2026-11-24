from dataclasses import dataclass

from issue.support import SupportSpan, validate_support
from station.observations import require_number, require_text


@dataclass(frozen=True)
class PieceOrigin:
    batch_id: str
    bench_id: str
    role: str
    unit: str
    revision_no: int


@dataclass(frozen=True)
class FrozenPiece:
    version: int
    issue_id: str
    origin: PieceOrigin
    support: tuple[SupportSpan, ...]


def build_envelope(
    issue_id: str, origin: PieceOrigin, support: tuple[SupportSpan, ...],
) -> FrozenPiece:
    piece = FrozenPiece(1, issue_id, origin, support)
    validate_envelope(piece)
    return piece


def validate_envelope(piece: FrozenPiece) -> None:
    if not isinstance(piece, FrozenPiece) or type(piece.version) is not int or piece.version != 1:
        raise ValueError('unsupported frozen piece envelope')
    require_text(piece.issue_id, 'issue id')
    origin = piece.origin
    if not isinstance(origin, PieceOrigin):
        raise ValueError('frozen piece requires an origin')
    require_text(origin.batch_id, 'origin batch id')
    require_text(origin.bench_id, 'origin bench id')
    require_text(origin.unit, 'origin unit')
    require_number(origin.revision_no, 'origin revision number')
    if origin.role not in ('A', 'B'):
        raise ValueError('frozen piece role must be A or B')
    validate_support(piece.support)
