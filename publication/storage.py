import json
import sqlite3
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from analysis.lag_set import LagInterval
from analysis.minima import ReviewDecision
from analysis.request import ReviewRequest
from issue.envelope import PieceOrigin
from publication.lineage import ParentReference
from publication.receipts import SuccessReceipt, make_success_receipt


@dataclass(frozen=True)
class ReportRecord:
    report_no: int
    request: ReviewRequest
    decision: ReviewDecision
    parents: tuple[ParentReference, ParentReference]
    receipt: SuccessReceipt


class PublicationStore:
    def __init__(self, path: str | Path):
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        try:
            self._db.execute('PRAGMA foreign_keys = ON')
            self.initialize()
        except BaseException:
            self._db.close()
            raise

    def initialize(self) -> None:
        self._db.executescript('''
            CREATE TABLE IF NOT EXISTS reports (
                report_no INTEGER PRIMARY KEY AUTOINCREMENT,
                a_receipt INTEGER NOT NULL,
                b_receipt INTEGER NOT NULL,
                lag_start TEXT NOT NULL,
                lag_end TEXT NOT NULL,
                minimum_coverage TEXT NOT NULL,
                intervals TEXT NOT NULL,
                minimum_mse TEXT
            );
            CREATE TABLE IF NOT EXISTS report_parents (
                report_no INTEGER NOT NULL REFERENCES reports(report_no),
                position INTEGER NOT NULL CHECK (position IN (0, 1)),
                receipt_no INTEGER NOT NULL,
                issue_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                bench_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('A', 'B')),
                unit TEXT NOT NULL,
                revision_no INTEGER NOT NULL,
                PRIMARY KEY (report_no, position)
            );
            CREATE TABLE IF NOT EXISTS success_receipts (
                report_no INTEGER PRIMARY KEY REFERENCES reports(report_no),
                receipt_id TEXT UNIQUE NOT NULL
            );
        ''')

    def commit_report(
        self,
        request: ReviewRequest,
        decision: ReviewDecision,
        parents: tuple[ParentReference, ParentReference],
    ) -> ReportRecord:
        if tuple(parent.receipt_no for parent in parents) != (request.a_receipt, request.b_receipt):
            raise ValueError('report parents must match the requested receipts in order')
        intervals = json.dumps([[str(interval.start), str(interval.end)] for interval in decision.intervals])
        minimum = None if decision.minimum_mse is None else str(decision.minimum_mse)
        with self._db:
            cursor = self._db.execute('''
                INSERT INTO reports (
                    a_receipt, b_receipt, lag_start, lag_end, minimum_coverage, intervals, minimum_mse
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                request.a_receipt, request.b_receipt, str(request.window.start),
                str(request.window.end), str(request.minimum_coverage), intervals, minimum,
            ))
            report_no = cursor.lastrowid
            self._db.executemany('''
                INSERT INTO report_parents (
                    report_no, position, receipt_no, issue_id, batch_id, bench_id, role, unit, revision_no
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                (report_no, position, parent.receipt_no, parent.issue_id, parent.origin.batch_id,
                 parent.origin.bench_id, parent.origin.role, parent.origin.unit, parent.origin.revision_no)
                for position, parent in enumerate(parents)
            ))
            receipt = make_success_receipt(report_no)
            self._db.execute('''
                INSERT INTO success_receipts (report_no, receipt_id) VALUES (?, ?)
            ''', (receipt.report_no, receipt.receipt_id))
        return ReportRecord(report_no, request, decision, parents, receipt)

    def load_report(self, report_no: int) -> ReportRecord | None:
        row = self._db.execute('''
            SELECT reports.*, success_receipts.receipt_id
            FROM reports JOIN success_receipts USING (report_no)
            WHERE reports.report_no = ?
        ''', (report_no,)).fetchone()
        if row is None:
            return None
        parent_rows = self._db.execute('''
            SELECT receipt_no, issue_id, batch_id, bench_id, role, unit, revision_no
            FROM report_parents WHERE report_no = ? ORDER BY position
        ''', (report_no,))
        a_parent, b_parent = (
            ParentReference(receipt_no, issue_id, PieceOrigin(batch_id, bench_id, role, unit, revision_no))
            for receipt_no, issue_id, batch_id, bench_id, role, unit, revision_no in parent_rows
        )
        request = ReviewRequest(
            row['a_receipt'], row['b_receipt'],
            LagInterval(Fraction(row['lag_start']), Fraction(row['lag_end'])),
            Fraction(row['minimum_coverage']),
        )
        minimum = row['minimum_mse']
        decision = ReviewDecision(
            tuple(LagInterval(Fraction(start), Fraction(end)) for start, end in json.loads(row['intervals'])),
            None if minimum is None else Fraction(minimum),
        )
        receipt = SuccessReceipt(row['receipt_id'], report_no)
        return ReportRecord(report_no, request, decision, (a_parent, b_parent), receipt)

    def close(self) -> None:
        self._db.close()
