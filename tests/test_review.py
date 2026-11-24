import sqlite3
from contextlib import closing
from fractions import Fraction as F

from analysis.request import review
from intake.receive import receive_piece
from issue.codec import encode_piece
from issue.envelope import PieceOrigin, build_envelope
from issue.support import SupportSpan
from publication.history import get_report
from publication.storage import PublicationStore
from tests.test_handoff import StationCase


class ReviewCase(StationCase):
    def setUp(self):
        super().setUp()
        self.publication_path = self.root / 'publication.db'
        self.open_publication()

    def open_publication(self):
        self.publication = PublicationStore(self.publication_path)
        self.addCleanup(self.publication.close)

    def issue_counts(self):
        with closing(sqlite3.connect(self.publication_path)) as db:
            return tuple(db.execute(sql).fetchone()[0] for sql in (
                'SELECT COUNT(*) FROM reports',
                'SELECT COUNT(*) FROM report_parents',
                'SELECT COUNT(*) FROM success_receipts',
            ))

    def assert_decision(self, report, expected_intervals, expected_mse):
        self.assertEqual(tuple((span.start, span.end) for span in report.decision.intervals), expected_intervals)
        self.assertEqual(report.decision.minimum_mse, expected_mse)
        for span in report.decision.intervals:
            self.assertIsInstance(span.start, F)
            self.assertIsInstance(span.end, F)
        if expected_mse is not None:
            self.assertIsInstance(report.decision.minimum_mse, F)

    def assert_parents(self, report, a, b):
        self.assertEqual(tuple(parent.receipt_no for parent in report.parents), (a.receipt_no, b.receipt_no))
        self.assertEqual(tuple(parent.issue_id for parent in report.parents), (a.piece.issue_id, b.piece.issue_id))
        self.assertEqual(tuple(parent.origin for parent in report.parents), (a.origin, b.origin))

    def independent_receipt(self, issue_id, role, spans, *, batch_id=None, bench=None, unit=None):
        if bench is None:
            bench = self.a_bench if role == 'A' else self.b_bench
        origin = PieceOrigin(batch_id or self.batch_id, bench, role, unit or self.unit, 81)
        support = tuple(SupportSpan(F(start), F(end), F(value)) for start, end, value in spans)
        return receive_piece(self.intake, encode_piece(build_envelope(issue_id, origin, support)))


class TestReview(ReviewCase):
    def test_minimum_at_coverage_boundary(self):
        a, b = self.original_pair()
        self.stop_source()
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, **self.sample['request'])
        # For s in [0,1], C=2-s and N=4(1-s). For s in [1,2], C=1.
        self.assert_decision(report, ((F('1/2'), F('1/2')),), F('4/3'))
        self.assert_parents(report, a, b)
        self.assertEqual(get_report(self.publication, report.report_no), report)
        self.assertEqual(self.issue_counts(), (1, 2, 1))

    def test_independent_evidence(self):
        self.stop_source()
        a = self.independent_receipt('independent:A', 'A', [(0, 2, 0), (3, 4, 4)])
        b = self.independent_receipt('independent:B', 'B', [(0, 1, 0), (1, 2, 2)])
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, 0, 2, '3/2')
        self.assert_decision(report, ((F('1/2'), F('1/2')),), F('4/3'))
        self.assert_parents(report, a, b)

    def test_floor_equal(self):
        a, b = self.original_pair()
        self.stop_source()
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, 0, 2, 2)
        self.assert_decision(report, ((F(0), F(0)),), F(2))

    def test_disconnected_equal_minima(self):
        a = self.deliver(self.a_bench, [(0, 2, 0), (4, 6, 0)])
        b = self.deliver(self.b_bench, [(0, 2, 0)])
        self.stop_source()
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, -1, 5, '3/2')
        # Each two-second support permits a displacement of at most half a second from full overlap.
        self.assert_decision(report, ((F('-1/2'), F('1/2')), (F('7/2'), F('9/2'))), F(0))
        self.assertEqual(get_report(self.publication, report.report_no), report)

    def test_invalid_request(self):
        a, b = self.original_pair()
        self.stop_source()
        inputs = ((2, 0, 1), (0, 2, 0), (0, 2, -1), (0, 2, '1/0'), (True, 2, 1), (0, 2, 0.5))
        for args in inputs:
            with self.subTest(args=args), self.assertRaises(ValueError):
                review(self.intake, self.publication, a.receipt_no, b.receipt_no, *args)
        with self.assertRaises(LookupError):
            review(self.intake, self.publication, a.receipt_no, b.receipt_no + 100, 0, 2, 1)
        self.assertEqual(self.issue_counts(), (0, 0, 0))

    def test_no_qualifying_lag(self):
        a, b = self.original_pair()
        self.stop_source()
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, 0, 2, '5/2')
        self.assert_decision(report, (), None)
        self.assertEqual(report.receipt.report_no, report.report_no)
        self.assertEqual(report.request.minimum_coverage, F('5/2'))
        self.assert_parents(report, a, b)
        self.assertEqual(get_report(self.publication, report.report_no), report)
        self.assertEqual(self.issue_counts(), (1, 2, 1))

    def test_empty_support(self):
        a = self.deliver(self.a_bench, [(0, 4, None)])
        b = self.deliver(self.b_bench, self.sample['b_original'])
        self.stop_source()
        self.assertEqual(a.piece.support, ())
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, 0, 2, 1)
        self.assert_decision(report, (), None)
        self.assert_parents(report, a, b)
        self.assertEqual(report.receipt.report_no, report.report_no)
        self.assertEqual(get_report(self.publication, report.report_no), report)
        self.assertEqual(self.issue_counts(), (1, 2, 1))

    def test_wrong_batch(self):
        a, b = self.original_pair()
        other = 'LC-other'
        from station.batches import register_batch
        from station.revisions import record_revision
        from issue.freeze import issue_piece

        register_batch(self.station, other, self.a_bench, self.b_bench, self.unit)
        revision = record_revision(self.station, other, self.b_bench, self.sample['b_original'])
        other_b = receive_piece(self.intake, issue_piece(self.station, self.archive, other, self.b_bench, revision))
        self.stop_source()
        with self.assertRaisesRegex(ValueError, 'same batch'):
            review(self.intake, self.publication, a.receipt_no, other_b.receipt_no, 0, 2, '3/2')
        self.assertEqual(self.issue_counts(), (0, 0, 0))
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, 0, 2, '3/2')
        self.assert_parents(report, a, b)
        self.assert_decision(report, ((F('1/2'), F('1/2')),), F('4/3'))

    def test_reversed_roles(self):
        a, b = self.original_pair()
        self.stop_source()
        with self.assertRaisesRegex(ValueError, 'A receipt followed by the B receipt'):
            review(self.intake, self.publication, b.receipt_no, a.receipt_no, 0, 2, 1)
        self.assertEqual(self.issue_counts(), (0, 0, 0))

    def test_incompatible_unit_or_bench(self):
        a, _ = self.original_pair()
        self.stop_source()
        wrong_unit = self.independent_receipt('wrong:unit', 'B', [(0, 2, 1)], unit='N')
        wrong_bench = self.independent_receipt('wrong:bench', 'B', [(0, 2, 1)], bench=self.a_bench)
        for invalid, pattern in ((wrong_unit, 'matching reading units'), (wrong_bench, 'two distinct benches')):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                review(self.intake, self.publication, a.receipt_no, invalid.receipt_no, 0, 2, 1)
        self.assertEqual(self.issue_counts(), (0, 0, 0))

    def test_single_negative_lag_with_fractional_values(self):
        a = self.deliver(self.a_bench, [('-1/3', '2/3', '1/4')])
        b = self.deliver(self.b_bench, [(0, 1, '3/4')])
        self.stop_source()
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, '-1/3', '-1/3', 1)
        self.assert_decision(report, ((F('-1/3'), F('-1/3')),), F('1/4'))
