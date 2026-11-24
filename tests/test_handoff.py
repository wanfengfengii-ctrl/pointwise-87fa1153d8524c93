import json
import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
from tempfile import TemporaryDirectory

from intake.catalog import load_received_piece
from intake.receive import receive_piece
from intake.storage import IntakeStore
from issue.archive import IssueArchive
from issue.codec import decode_piece, encode_piece
from issue.freeze import issue_piece
from issue.support import SupportSpan
from station.batches import load_batch, register_batch
from station.revisions import load_revision, record_revision
from station.storage import StationStore


class StationCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.station_path = self.root / 'station.db'
        self.archive_path = self.root / 'issue.db'
        self.intake_path = self.root / 'intake.db'
        self.open_source()
        self.intake = IntakeStore(self.intake_path)
        self.addCleanup(self.intake.close)
        sample_path = Path(__file__).resolve().parents[1] / 'samples' / 'shift.json'
        self.sample = json.loads(sample_path.read_text(encoding='utf-8'))
        self.batch_id = self.sample['batch_id']
        self.a_bench, self.b_bench = self.sample['benches']
        self.unit = self.sample['unit']
        register_batch(self.station, self.batch_id, self.a_bench, self.b_bench, self.unit)

    def open_source(self):
        self.station = StationStore(self.station_path)
        self.addCleanup(self.station.close)
        self.archive = IssueArchive(self.archive_path, 'lichuan-test')
        self.addCleanup(self.archive.close)

    def stop_source(self):
        self.archive.close()
        self.station.close()

    def deliver(self, bench_id, rows):
        revision_no = record_revision(self.station, self.batch_id, bench_id, rows)
        piece = issue_piece(self.station, self.archive, self.batch_id, bench_id, revision_no)
        return receive_piece(self.intake, encode_piece(piece))

    def original_pair(self):
        return (
            self.deliver(self.a_bench, self.sample['a_original']),
            self.deliver(self.b_bench, self.sample['b_original']),
        )

    def revision_counts(self):
        with closing(sqlite3.connect(self.station_path)) as db:
            return tuple(db.execute(sql).fetchone()[0] for sql in (
                'SELECT COUNT(*) FROM revisions', 'SELECT COUNT(*) FROM observations',
            ))

    def intake_count(self):
        with closing(sqlite3.connect(self.intake_path)) as db:
            return db.execute('SELECT COUNT(*) FROM received_pieces').fetchone()[0]


class TestHandoff(StationCase):
    def test_receive_frozen_pair(self):
        a, b = self.original_pair()
        self.assertNotEqual(a.receipt_no, b.receipt_no)
        for receipt, bench, role in ((a, self.a_bench, 'A'), (b, self.b_bench, 'B')):
            with self.subTest(role=role):
                origin = receipt.origin
                self.assertEqual((origin.batch_id, origin.bench_id, origin.role, origin.unit),
                                 (self.batch_id, bench, role, self.unit))
                self.assertEqual(self.archive.load_piece(receipt.piece.issue_id), receipt.piece)
                archived = encode_piece(receipt.piece)
                self.assertEqual(decode_piece(archived), receipt.piece)
                self.assertEqual(receive_piece(self.intake, archived), receipt)
                self.assertEqual(load_received_piece(self.intake, receipt.receipt_no), receipt)
                obj = json.loads(archived)
                self.assertEqual(set(obj['origin']), {'batch_id', 'bench_id', 'role', 'unit', 'revision_no'})
        self.assertEqual(a.piece.support, (SupportSpan(F(0), F(2), F(0)), SupportSpan(F(3), F(4), F(4))))
        self.assertEqual(b.piece.support, (SupportSpan(F(0), F(1), F(0)), SupportSpan(F(1), F(2), F(2))))
        self.assertEqual(self.intake_count(), 2)

    def test_init_reentry(self):
        a, b = self.original_pair()
        for _ in range(2):
            self.station.initialize()
            self.archive.initialize()
            self.intake.initialize()
        self.assertEqual(register_batch(self.station, self.batch_id, self.a_bench, self.b_bench, self.unit),
                         self.batch_id)
        with self.assertRaises(ValueError):
            register_batch(self.station, self.batch_id, self.b_bench, self.a_bench, self.unit)
        with self.assertRaises(ValueError):
            IssueArchive(self.archive_path, 'different-issuer')
        batch = load_batch(self.station, self.batch_id)
        self.assertEqual((batch.a_bench, batch.b_bench, batch.unit), (self.a_bench, self.b_bench, self.unit))
        for received in (a, b):
            revision = load_revision(self.station, self.batch_id, received.origin.bench_id, received.origin.revision_no)
            self.assertEqual(revision.revision_no, received.origin.revision_no)
            self.assertEqual(self.archive.load_piece(received.piece.issue_id), received.piece)
            self.assertEqual(receive_piece(self.intake, received.piece), received)
        corrected = self.deliver(self.a_bench, self.sample['a_corrected'])
        self.assertGreater(corrected.origin.revision_no, b.origin.revision_no)
        self.assertGreater(corrected.receipt_no, b.receipt_no)
        self.assertNotIn(corrected.piece.issue_id, (a.piece.issue_id, b.piece.issue_id))
        self.assertEqual(self.intake_count(), 3)

    def test_evidence_distinguishes_gap(self):
        original = self.deliver(self.a_bench, self.sample['a_original'])
        corrected = self.deliver(self.a_bench, self.sample['a_corrected'])
        self.assertNotEqual(original.origin.revision_no, corrected.origin.revision_no)
        self.assertNotEqual(original.piece.issue_id, corrected.piece.issue_id)
        self.assertNotEqual(original.receipt_no, corrected.receipt_no)
        self.assertEqual(json.loads(encode_piece(original.piece))['support'], [['0', '2', '0'], ['3', '4', '4']])
        self.assertEqual(json.loads(encode_piece(corrected.piece))['support'],
                         [['0', '2', '0'], ['2', '3', '0'], ['3', '4', '4']])
        self.stop_source()
        for receipt, expected_duration in ((original, 3), (corrected, 4)):
            persisted = load_received_piece(self.intake, receipt.receipt_no)
            self.assertEqual(persisted, receipt)
            self.assertEqual(sum(span.end - span.start for span in persisted.piece.support), expected_duration)

    def assert_revision_rejected(self, rows):
        original = record_revision(self.station, self.batch_id, self.a_bench, self.sample['a_original'])
        counts = self.revision_counts()
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            record_revision(self.station, self.batch_id, self.a_bench, rows)
        self.assertEqual(self.revision_counts(), counts)
        piece = issue_piece(self.station, self.archive, self.batch_id, self.a_bench, original)
        self.assertEqual(piece.origin.revision_no, original)
        self.assertEqual(piece.support, (SupportSpan(F(0), F(2), F(0)), SupportSpan(F(3), F(4), F(4))))

    def test_reject_overlap(self):
        self.assert_revision_rejected([(0, 2, 0), (0, 3, 4)])

    def test_reject_shifted_overlap(self):
        self.assert_revision_rejected([(1, 3, 4), (0, 2, 0)])

    def test_invalid_revision_is_atomic(self):
        original = self.deliver(self.a_bench, [(1, 2, '1/3'), ('-1/2', 1, None)])
        initial = self.revision_counts()
        invalid = (
            [(0, 2, 0), (3, 3, 4)],
            [(0, 2, 0), (2, 3, '1/0')],
            [(0, 2, 0.5)],
            [(0, 1, None), ('1/2', 2, 0)],
        )
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                record_revision(self.station, self.batch_id, self.a_bench, rows)
        with self.assertRaises(ValueError):
            record_revision(self.station, self.batch_id, 'unregistered-bench', [(0, 1, 0)])
        self.assertEqual(self.revision_counts(), initial)
        revision = load_revision(self.station, self.batch_id, self.a_bench, original.origin.revision_no)
        self.assertEqual([(row.start, row.end, row.value) for row in revision.observations],
                         [(F('-1/2'), F(1), None), (F(1), F(2), F('1/3'))])

    def test_conflicting_delivery(self):
        a, _ = self.original_pair()
        spans = a.piece.support
        changed_body = replace(a.piece, support=(replace(spans[0], value=F(7)), *spans[1:]))
        changed_origin = replace(a.piece, origin=replace(a.origin, unit='N'))
        for conflicting in (changed_body, changed_origin):
            with self.subTest(piece=conflicting), self.assertRaisesRegex(ValueError, 'conflicting delivery'):
                receive_piece(self.intake, encode_piece(conflicting))
        self.assertEqual(load_received_piece(self.intake, a.receipt_no), a)
        self.assertEqual(receive_piece(self.intake, a.piece), a)
        self.assertEqual(self.intake_count(), 2)

    def test_invalid_envelope_is_not_received(self):
        a, _ = self.original_pair()
        good = json.loads(encode_piece(a.piece))
        invalid = (
            b'not a frozen piece',
            b'{"version":1,"version":1}',
            json.dumps(good | {'version': True}).encode(),
            json.dumps(good | {'support': [['0', '2', '0'], ['1', '3', '4']]}).encode(),
            json.dumps(good | {'support': [['0', '2', None]]}).encode(),
        )
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                receive_piece(self.intake, payload)
        reformatted = json.dumps(good | {'support': [['0/2', '2', '0'], ['3', '4', '4']]}, indent=2).encode()
        self.assertEqual(receive_piece(self.intake, reformatted), a)
        self.assertEqual(load_received_piece(self.intake, a.receipt_no), a)
        self.assertEqual(self.intake_count(), 2)
