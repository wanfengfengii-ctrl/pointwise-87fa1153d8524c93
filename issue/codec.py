import json
from fractions import Fraction

from issue.envelope import FrozenPiece, PieceOrigin, validate_envelope
from issue.support import SupportSpan
from station.observations import parse_rational


_ENVELOPE_FIELDS = {'version', 'issue_id', 'origin', 'support'}
_ORIGIN_FIELDS = {'batch_id', 'bench_id', 'role', 'unit', 'revision_no'}


def encode_piece(piece: FrozenPiece) -> bytes:
    validate_envelope(piece)
    origin = piece.origin
    payload = {
        'version': piece.version,
        'issue_id': piece.issue_id,
        'origin': {
            'batch_id': origin.batch_id,
            'bench_id': origin.bench_id,
            'role': origin.role,
            'unit': origin.unit,
            'revision_no': origin.revision_no,
        },
        'support': [[str(span.start), str(span.end), str(span.value)] for span in piece.support],
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate frozen piece field {key!r}')
        result[key] = value
    return result


def _wire_rational(value: object) -> Fraction:
    if not isinstance(value, str):
        raise ValueError('frozen span numbers must be encoded as text')
    return parse_rational(value, 'frozen span number')


def decode_piece(payload: bytes) -> FrozenPiece:
    if not isinstance(payload, bytes):
        raise ValueError('frozen piece payload must be bytes')
    try:
        fields = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError('invalid frozen piece JSON') from exc
    if not isinstance(fields, dict) or fields.keys() != _ENVELOPE_FIELDS:
        raise ValueError('invalid frozen piece fields')
    origin = fields['origin']
    if not isinstance(origin, dict) or origin.keys() != _ORIGIN_FIELDS:
        raise ValueError('invalid frozen piece origin fields')
    support = fields['support']
    if not isinstance(support, list):
        raise ValueError('invalid frozen piece support')
    spans = []
    for row in support:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError('frozen span must have start, end and value')
        start, end, value = map(_wire_rational, row)
        spans.append(SupportSpan(start, end, value))
    piece = FrozenPiece(fields['version'], fields['issue_id'], PieceOrigin(**origin), tuple(spans))
    validate_envelope(piece)
    return piece
