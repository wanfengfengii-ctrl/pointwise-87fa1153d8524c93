import sqlite3
from fractions import Fraction
from pathlib import Path

from station.observations import Observation


class StationStore:
    def __init__(self, path: str | Path):
        self._db = sqlite3.connect(path)
        try:
            self._db.execute('PRAGMA foreign_keys = ON')
            self.initialize()
        except BaseException:
            self._db.close()
            raise

    def initialize(self) -> None:
        self._db.executescript('''
            CREATE TABLE IF NOT EXISTS batches (
                batch_id TEXT PRIMARY KEY NOT NULL,
                a_bench TEXT NOT NULL,
                b_bench TEXT NOT NULL,
                unit TEXT NOT NULL,
                CHECK (a_bench <> b_bench)
            );
            CREATE TABLE IF NOT EXISTS revisions (
                revision_no INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                bench_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observations (
                revision_no INTEGER NOT NULL REFERENCES revisions(revision_no),
                ordinal INTEGER NOT NULL,
                start TEXT NOT NULL,
                end TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (revision_no, ordinal)
            );
        ''')

    def write_batch(
        self, batch_id: str, a_bench: str, b_bench: str, unit: str,
    ) -> tuple[str, str, str, str]:
        with self._db:
            self._db.execute('''
                INSERT INTO batches (batch_id, a_bench, b_bench, unit)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (batch_id) DO NOTHING
            ''', (batch_id, a_bench, b_bench, unit))
            saved = self.read_batch(batch_id)
        return saved

    def read_batch(self, batch_id: str) -> tuple[str, str, str, str] | None:
        return self._db.execute('''
            SELECT batch_id, a_bench, b_bench, unit FROM batches WHERE batch_id = ?
        ''', (batch_id,)).fetchone()

    def save_revision(
        self, batch_id: str, bench_id: str, observations: tuple[Observation, ...],
    ) -> int:
        with self._db:
            cursor = self._db.execute('''
                INSERT INTO revisions (batch_id, bench_id) VALUES (?, ?)
            ''', (batch_id, bench_id))
            revision_no = cursor.lastrowid
            self._db.executemany('''
                INSERT INTO observations (revision_no, ordinal, start, end, value)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                (revision_no, ordinal, str(row.start), str(row.end),
                 None if row.value is None else str(row.value))
                for ordinal, row in enumerate(observations)
            ))
        return revision_no

    def read_revision(
        self, batch_id: str, bench_id: str, revision_no: int,
    ) -> tuple[Observation, ...] | None:
        header = self._db.execute('''
            SELECT revision_no FROM revisions
            WHERE revision_no = ? AND batch_id = ? AND bench_id = ?
        ''', (revision_no, batch_id, bench_id)).fetchone()
        if header is None:
            return None
        rows = self._db.execute('''
            SELECT start, end, value FROM observations
            WHERE revision_no = ? ORDER BY ordinal
        ''', (revision_no,))
        return tuple(
            Observation(Fraction(start), Fraction(end), None if value is None else Fraction(value))
            for start, end, value in rows
        )

    def close(self) -> None:
        self._db.close()
