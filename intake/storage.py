import sqlite3
from pathlib import Path


class IntakeStore:
    def __init__(self, path: str | Path):
        self._db = sqlite3.connect(path)
        try:
            self.initialize()
        except BaseException:
            self._db.close()
            raise

    def initialize(self) -> None:
        self._db.execute('''
            CREATE TABLE IF NOT EXISTS received_pieces (
                receipt_no INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id TEXT UNIQUE NOT NULL,
                payload BLOB NOT NULL
            )
        ''')

    def reconcile_delivery(self, issue_id: str, payload: bytes) -> int:
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            original = self._db.execute('''
                SELECT receipt_no, payload FROM received_pieces WHERE issue_id = ?
            ''', (issue_id,)).fetchone()
            if original is not None:
                receipt_no, accepted_payload = original
                if accepted_payload != payload:
                    raise ValueError(f'conflicting delivery of issue {issue_id!r}')
                return receipt_no
            cursor = self._db.execute('''
                INSERT INTO received_pieces (issue_id, payload) VALUES (?, ?)
            ''', (issue_id, payload))
            receipt_no = cursor.lastrowid
        return receipt_no

    def fetch_received(self, receipt_no: int) -> bytes | None:
        row = self._db.execute('''
            SELECT payload FROM received_pieces WHERE receipt_no = ?
        ''', (receipt_no,)).fetchone()
        return None if row is None else row[0]

    def close(self) -> None:
        self._db.close()
