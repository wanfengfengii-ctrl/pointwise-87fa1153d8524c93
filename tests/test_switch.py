import json
import sqlite3
from contextlib import closing
from fractions import Fraction as F
from pathlib import Path

from analysis.convex import ConvexRegion
from analysis.request import review, review_switch
from intake.receive import receive_piece
from issue.codec import encode_piece
from issue.freeze import issue_piece
from publication.history import get_report
from publication.storage import PublicationStore
from station.batches import register_batch
from station.revisions import record_revision
from tests.test_review import ReviewCase


class SwitchCase(ReviewCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sample_path = Path(__file__).resolve().parents[1] / 'samples' / 'switch.json'
        cls.switch_sample = json.loads(sample_path.read_text(encoding='utf-8'))

    def case(self, batch_id):
        for entry in self.switch_sample['cases']:
            if entry['batch_id'] == batch_id:
                return entry
        raise KeyError(batch_id)

    def deliver_switch(self, case):
        register_batch(
            self.station, case['batch_id'], self.a_bench, self.b_bench, self.unit,
        )
        a_revision = record_revision(self.station, case['batch_id'], self.a_bench, case['a_rows'])
        b_revision = record_revision(self.station, case['batch_id'], self.b_bench, case['b_rows'])
        a = receive_piece(
            self.intake,
            encode_piece(issue_piece(self.station, self.archive, case['batch_id'], self.a_bench, a_revision)),
        )
        b = receive_piece(
            self.intake,
            encode_piece(issue_piece(self.station, self.archive, case['batch_id'], self.b_bench, b_revision)),
        )
        return a, b

    def sign(self, a, b, request, **overrides):
        arguments = dict(request, **overrides)
        return review_switch(
            self.intake,
            self.publication,
            a.receipt_no,
            b.receipt_no,
            arguments['cut'],
            arguments['before_window'],
            arguments['after_window'],
            arguments['max_change'],
            arguments['minimum_coverage'],
        )

    def reopen_publication(self):
        self.publication.close()
        self.publication = PublicationStore(self.publication_path)
        self.addCleanup(self.publication.close)

    def assert_hulls(self, report, hulls):
        expected = tuple(
            ConvexRegion(tuple((F(x), F(y)) for x, y in hull)) for hull in hulls
        )
        self.assertEqual(report.decision.regions, expected)

    def assert_switch_request(self, report, request):
        self.assertEqual(report.request.a_receipt, report.parents[0].receipt_no)
        self.assertEqual(report.request.b_receipt, report.parents[1].receipt_no)
        self.assertEqual(report.request.cut, F(request['cut']))
        self.assertEqual(
            (report.request.before_window.start, report.request.before_window.end),
            (F(request['before_window'][0]), F(request['before_window'][1])),
        )
        self.assertEqual(
            (report.request.after_window.start, report.request.after_window.end),
            (F(request['after_window'][0]), F(request['after_window'][1])),
        )
        self.assertEqual(report.request.max_change, F(request['max_change']))
        self.assertEqual(report.request.minimum_coverage, F(request['minimum_coverage']))
        self.assertIsInstance(report.request.cut, F)
        self.assertIsInstance(report.request.minimum_coverage, F)
        self.assertIsInstance(report.request.max_change, F)


class TestSwitchSamples(SwitchCase):
    def test_each_sample_case(self):
        for case in self.switch_sample['cases']:
            with self.subTest(batch=case['batch_id']):
                a, b = self.deliver_switch(case)
                self.stop_source()
                report = self.sign(a, b, case['request'])
                expected = case['expected']
                self.assertEqual(report.decision.minimum_mse, F(expected['minimum_mse']))
                self.assert_hulls(report, expected['hulls'])
                self.assert_switch_request(report, case['request'])
                self.assert_parents(report, a, b)
                self.assertEqual(report.receipt.report_no, report.report_no)
                self.assertEqual(get_report(self.publication, report.report_no), report)
                self.open_source()

    def test_limit_domain(self):
        case = self.case('LC-switch-limit')
        a, b = self.deliver_switch(case)
        report = self.sign(a, b, case['request'])
        self.assertTrue(report.decision.contains(F(0), F('1/2')))
        self.assertTrue(report.decision.contains(F('1/2'), 1))
        self.assertTrue(report.decision.contains(F('1/4'), F('3/4')))
        self.assertFalse(report.decision.contains(0, 1))
        self.assertFalse(report.decision.contains(0, 0))
        self.assertFalse(report.decision.contains(F('1/2'), F('1/4')))

    def test_split_coverage_floor(self):
        case = self.case('LC-split-coverage')
        a, b = self.deliver_switch(case)
        report = self.sign(a, b, case['request'])
        self.assertEqual(report.decision.minimum_mse, 0)
        self.assertTrue(report.decision.contains(F(0), F('1/2')))
        self.assertTrue(report.decision.contains(F('1/2'), 1))
        raised = self.sign(a, b, case['request'], minimum_coverage=2)
        self.assertEqual(raised.decision.minimum_mse, None)
        self.assertEqual(raised.decision.regions, ())
        for pair in ((0, 0), (0, 1), (F('1/2'), F('1/2')), (F('1/4'), F('3/4')), (1, 1)):
            self.assertFalse(raised.decision.contains(*pair))
        self.assertEqual(get_report(self.publication, raised.report_no), raised)
        self.assert_switch_request(raised, dict(case['request'], minimum_coverage=2))

    def test_separated_and_flat(self):
        for batch, hulls in (
            ('LC-separated', [[[0, 0]], [[3, 3]]]),
            ('LC-flat', [[[0, 0], [0, '1/2'], ['1/2', 1], [1, 1]]]),
        ):
            with self.subTest(batch=batch):
                case = self.case(batch)
                a, b = self.deliver_switch(case)
                report = self.sign(a, b, case['request'])
                self.assert_hulls(report, hulls)
                self.assertEqual(get_report(self.publication, report.report_no), report)

    def test_separated_excludes_middle(self):
        case = self.case('LC-separated')
        a, b = self.deliver_switch(case)
        report = self.sign(a, b, case['request'])
        self.assertTrue(report.decision.contains(0, 0))
        self.assertTrue(report.decision.contains(3, 3))
        for pair in ((F('3/2'), F('3/2')), (1, 1), (2, 2), (0, 3), (3, 0)):
            self.assertFalse(report.decision.contains(*pair))

    def test_flat_region_is_two_dimensional(self):
        case = self.case('LC-flat')
        a, b = self.deliver_switch(case)
        report = self.sign(a, b, case['request'])
        self.assertEqual(len(report.decision.regions), 1)
        self.assertEqual(report.decision.regions[0].dimension, 2)
        self.assertTrue(report.decision.contains(F('1/4'), F('1/2')))

    def test_weighted_and_one_side(self):
        for batch, mse in (('LC-weighted', 6), ('LC-one-side', 0)):
            case = self.case(batch)
            a, b = self.deliver_switch(case)
            report = self.sign(a, b, case['request'])
            self.assertEqual(report.decision.minimum_mse, mse)
            self.assertEqual(report.decision.regions, (ConvexRegion(((F(0), F(0)),)),))


class TestSwitchPersistence(SwitchCase):
    def test_read_after_intake_and_publication_reopen(self):
        case = self.case('LC-switch-limit')
        a, b = self.deliver_switch(case)
        self.stop_source()
        report = self.sign(a, b, case['request'])
        self.intake.close()
        self.reopen_publication()
        self.publication.initialize()
        retrieved = get_report(self.publication, report.report_no)
        self.assertEqual(retrieved, report)
        self.assert_switch_request(retrieved, case['request'])
        self.assertEqual(retrieved.decision.minimum_mse, 1)
        self.assertTrue(retrieved.decision.contains(F('1/4'), F('3/4')))
        self.assertFalse(retrieved.decision.contains(0, 1))
        self.assertEqual(
            tuple((parent.receipt_no, parent.issue_id, parent.origin) for parent in retrieved.parents),
            tuple((parent.receipt_no, parent.issue_id, parent.origin) for parent in report.parents),
        )
        self.assertEqual(retrieved.receipt, report.receipt)

    def test_original_single_shift_report_still_readable(self):
        a, b = self.original_pair()
        case = self.case('LC-flat')
        a2, b2 = self.deliver_switch(case)
        self.stop_source()
        shifted = review(self.intake, self.publication, a.receipt_no, b.receipt_no, **self.sample['request'])
        switched = self.sign(a2, b2, case['request'])
        self.assertNotEqual(switched.report_no, shifted.report_no)
        self.intake.close()
        self.reopen_publication()
        self.assertEqual(get_report(self.publication, shifted.report_no), shifted)
        self.assertEqual(get_report(self.publication, switched.report_no), switched)
        self.assertEqual(
            tuple((span.start, span.end) for span in shifted.decision.intervals), ((F('1/2'), F('1/2')),),
        )
        self.assertEqual(shifted.decision.minimum_mse, F('4/3'))
        self.assertEqual(
            get_report(self.publication, switched.report_no).decision.minimum_mse, 0,
        )

    def test_empty_switch_decision_persisted(self):
        case = self.case('LC-split-coverage')
        a, b = self.deliver_switch(case)
        self.stop_source()
        report = self.sign(a, b, case['request'], minimum_coverage=2)
        self.intake.close()
        self.reopen_publication()
        retrieved = get_report(self.publication, report.report_no)
        self.assertEqual(retrieved, report)
        self.assertIsNone(retrieved.decision.minimum_mse)
        self.assertEqual(retrieved.decision.regions, ())
        self.assertFalse(retrieved.decision.contains(0, 0))
        self.assertEqual(self.issue_counts(), (1, 2, 1))


class TestSwitchFailure(SwitchCase):
    def install_commit_barrier(self):
        with closing(sqlite3.connect(self.publication_path)) as db:
            db.executescript('''
                CREATE TABLE commit_barrier (
                    impossible_parent INTEGER NOT NULL REFERENCES reports(report_no)
                    DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TRIGGER reject_next_success AFTER INSERT ON success_receipts
                BEGIN
                    INSERT INTO commit_barrier (impossible_parent) VALUES (-1);
                END;
            ''')

    def test_atomic_switch_commit(self):
        case = self.case('LC-switch-limit')
        a, b = self.deliver_switch(case)
        self.stop_source()
        old = self.sign(a, b, case['request'])
        original_counts = self.issue_counts()
        self.assertEqual(original_counts, (1, 2, 1))
        self.install_commit_barrier()
        with self.assertRaises(sqlite3.IntegrityError):
            self.sign(a, b, case['request'])
        self.assertEqual(self.issue_counts(), original_counts)
        self.reopen_publication()
        with closing(sqlite3.connect(self.publication_path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commit_barrier').fetchone()[0], 0)
        self.assertEqual(get_report(self.publication, old.report_no), old)
        self.assertIsNone(get_report(self.publication, old.report_no + 1))

    def test_invalid_switch_request(self):
        case = self.case('LC-switch-limit')
        a, b = self.deliver_switch(case)
        self.stop_source()
        request = case['request']
        invalid = (
            dict(request, before_window=(1, 0)),
            dict(request, after_window=[0]),
            dict(request, before_window='0..1'),
            dict(request, max_change=-1),
            dict(request, minimum_coverage=0),
            dict(request, minimum_coverage=-1),
            dict(request, max_change=0.5),
            dict(request, cut='1/0'),
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.sign(a, b, request, **overrides)
        with self.assertRaises(LookupError):
            review_switch(
                self.intake, self.publication, a.receipt_no + 100, b.receipt_no,
                request['cut'], request['before_window'], request['after_window'],
                request['max_change'], request['minimum_coverage'],
            )
        with self.assertRaisesRegex(ValueError, 'A receipt followed by the B receipt'):
            review_switch(
                self.intake, self.publication, b.receipt_no, a.receipt_no,
                request['cut'], request['before_window'], request['after_window'],
                request['max_change'], request['minimum_coverage'],
            )
        self.assertEqual(self.issue_counts(), (0, 0, 0))

    def test_cut_after_all_support(self):
        case = {
            'batch_id': 'LC-switch-cut',
            'a_rows': [[0, 2, 0]],
            'b_rows': [[0, 1, 0]],
            'request': {
                'cut': 5,
                'before_window': [0, 1],
                'after_window': [0, 1],
                'max_change': 0,
                'minimum_coverage': 1,
            },
        }
        a, b = self.deliver_switch(case)
        report = self.sign(a, b, case['request'])
        # With an empty after-side, only the before overlap contributes; keeping
        # s1 == s2 confines the optimum to the diagonal, all at zero error.
        self.assertEqual(report.decision.minimum_mse, 0)
        self.assertEqual(
            report.decision.regions,
            (ConvexRegion(((F(0), F(0)), (F(1), F(1)))),),
        )
        self.assertTrue(report.decision.contains(0, 0))
        self.assertTrue(report.decision.contains(1, 1))
        self.assertTrue(report.decision.contains(F('1/2'), F('1/2')))
        self.assertFalse(report.decision.contains(0, 1))
        self.assertEqual(get_report(self.publication, report.report_no), report)
