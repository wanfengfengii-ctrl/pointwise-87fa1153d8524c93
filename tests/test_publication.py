import sqlite3
from contextlib import closing
from fractions import Fraction as F

from analysis.request import review
from issue.freeze import issue_piece
from issue.support import SupportSpan
from publication.history import get_report
from station.revisions import record_revision
from tests.test_review import ReviewCase


class TestPublication(ReviewCase):
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

    def exercise_commit_failure(self):
        a, b = self.original_pair()
        self.stop_source()
        request = (a.receipt_no, b.receipt_no, 0, 2, '3/2')
        old = review(self.intake, self.publication, *request)
        original_counts = self.issue_counts()
        self.assertEqual(original_counts, (1, 2, 1))
        self.install_commit_barrier()
        # The receipt insert triggers a deferred constraint. SQLite rejects COMMIT after staging all three records.
        with self.assertRaises(sqlite3.IntegrityError) as failed:
            review(self.intake, self.publication, *request)
        self.assertEqual(failed.exception.sqlite_errorcode, sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY)
        self.assertEqual(self.issue_counts(), original_counts)
        self.publication.close()
        self.open_publication()
        with closing(sqlite3.connect(self.publication_path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commit_barrier').fetchone()[0], 0)
        self.assertEqual(self.issue_counts(), original_counts)
        self.assertEqual(get_report(self.publication, old.report_no), old)
        self.assertIsNone(get_report(self.publication, old.report_no + 1))
        return old, request

    def test_commit_failure(self):
        self.exercise_commit_failure()

    def test_retry_after_rollback(self):
        old, request = self.exercise_commit_failure()
        with closing(sqlite3.connect(self.publication_path)) as db:
            db.executescript('DROP TRIGGER reject_next_success; DROP TABLE commit_barrier;')
        new = review(self.intake, self.publication, *request)
        self.assertEqual(self.issue_counts(), (2, 4, 2))
        self.assertNotEqual(new.report_no, old.report_no)
        self.assertNotEqual(new.receipt, old.receipt)
        self.assertEqual(new.parents, old.parents)
        self.assertEqual(new.decision, old.decision)
        self.assertEqual(get_report(self.publication, old.report_no), old)
        self.assertEqual(get_report(self.publication, new.report_no), new)

    def test_reopen_after_zero_correction(self):
        a, b = self.original_pair()
        self.stop_source()
        original = review(self.intake, self.publication, a.receipt_no, b.receipt_no, **self.sample['request'])
        self.assert_decision(original, ((F('1/2'), F('1/2')),), F('4/3'))
        self.assert_parents(original, a, b)
        self.open_source()
        corrected_a = self.deliver(self.a_bench, self.sample['a_corrected'])
        self.stop_source()
        corrected = review(self.intake, self.publication, corrected_a.receipt_no, b.receipt_no, **self.sample['request'])
        self.assert_decision(corrected, ((F(0), F(2)),), F(2))
        self.assert_parents(corrected, corrected_a, b)
        self.assertNotEqual(corrected.receipt, original.receipt)
        self.assertNotEqual(corrected.parents[0], original.parents[0])
        self.assertEqual(corrected.parents[1], original.parents[1])
        self.assertEqual(self.issue_counts(), (2, 4, 2))
        self.intake.close()
        self.publication.close()
        self.open_publication()
        self.publication.initialize()
        self.assertEqual(get_report(self.publication, original.report_no), original)
        self.assertEqual(get_report(self.publication, corrected.report_no), corrected)
        self.assertEqual(self.issue_counts(), (2, 4, 2))

    def test_exact_revision(self):
        a, b = self.original_pair()
        corrected = self.deliver(self.a_bench, self.sample['a_corrected'])
        old_again = issue_piece(self.station, self.archive, self.batch_id, self.a_bench, a.origin.revision_no)
        self.assertEqual(old_again.origin, a.origin)
        self.assertEqual(old_again.support, (SupportSpan(F(0), F(2), F(0)), SupportSpan(F(3), F(4), F(4))))
        self.assertNotEqual(old_again.support, corrected.piece.support)
        with closing(sqlite3.connect(self.archive_path)) as db:
            count = db.execute('SELECT COUNT(*) FROM issued_pieces').fetchone()[0]
            with self.assertRaises(LookupError):
                issue_piece(self.station, self.archive, self.batch_id, self.a_bench, corrected.origin.revision_no + 100)
            with self.assertRaises(LookupError):
                issue_piece(self.station, self.archive, self.batch_id, self.a_bench, b.origin.revision_no)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM issued_pieces').fetchone()[0], count)

    def test_unknown_report(self):
        a, b = self.original_pair()
        self.stop_source()
        report = review(self.intake, self.publication, a.receipt_no, b.receipt_no, 0, 2, '3/2')
        self.intake.close()
        self.publication.close()
        self.open_publication()
        self.assertIsNone(get_report(self.publication, report.report_no + 100))
        self.assertEqual(get_report(self.publication, report.report_no), report)
        self.assertEqual(self.issue_counts(), (1, 2, 1))
