import sqlite3
from pathlib import Path

from issue.codec import decode_piece, encode_piece
from issue.envelope import FrozenPiece, PieceOrigin, build_envelope
from issue.support import SupportSpan
from station.observations import require_text


class IssueArchive:
    def __init__(self, path: str | Path, issuer_id: str):
        self._issuer_id = require_text(issuer_id, 'issuer id')
        self._db = sqlite3.connect(path)
        try:
            self.initialize()
        except BaseException:
            self._db.close()
            raise

    def initialize(self) -> None:
        self._db.executescript('''
            CREATE TABLE IF NOT EXISTS archive_identity (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                issuer_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS issued_pieces (
                serial INTEGER PRIMARY KEY,
                issue_id TEXT UNIQUE NOT NULL,
                payload BLOB NOT NULL
            );
        ''')
        with self._db:
            self._db.execute('''
                INSERT INTO archive_identity (singleton, issuer_id) VALUES (1, ?)
                ON CONFLICT (singleton) DO NOTHING
            ''', (self._issuer_id,))
            identity = self._db.execute('''
                SELECT issuer_id FROM archive_identity WHERE singleton = 1
            ''').fetchone()
            if identity != (self._issuer_id,):
                raise ValueError('issuer id differs from the archive identity')

    def save_piece(
        self, origin: PieceOrigin, support: tuple[SupportSpan, ...],
    ) -> FrozenPiece:
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            (serial,) = self._db.execute('''
                SELECT COALESCE(MAX(serial), 0) + 1 FROM issued_pieces
            ''').fetchone()
            issue_id = f'{self._issuer_id}:{serial}'
            piece = build_envelope(issue_id, origin, support)
            self._db.execute('''
                INSERT INTO issued_pieces (serial, issue_id, payload) VALUES (?, ?, ?)
            ''', (serial, issue_id, encode_piece(piece)))
        return piece

    def load_piece(self, issue_id: str) -> FrozenPiece | None:
        require_text(issue_id, 'issue id')
        row = self._db.execute('''
            SELECT payload FROM issued_pieces WHERE issue_id = ?
        ''', (issue_id,)).fetchone()
        return None if row is None else decode_piece(row[0])

    def close(self) -> None:
        self._db.close()
