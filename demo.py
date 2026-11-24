import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.request import review
from intake.receive import receive_piece
from intake.storage import IntakeStore
from issue.archive import IssueArchive
from issue.codec import encode_piece
from issue.freeze import issue_piece
from publication.history import get_report
from publication.storage import PublicationStore, ReportRecord
from station.batches import register_batch
from station.revisions import record_revision
from station.storage import StationStore


def decision_data(report: ReportRecord) -> dict:
    decision = report.decision
    return {
        'intervals': [[str(span.start), str(span.end)] for span in decision.intervals],
        'mse': None if decision.minimum_mse is None else str(decision.minimum_mse),
    }


def history_data(report: ReportRecord) -> dict:
    return {
        'report_no': report.report_no,
        'decision': decision_data(report),
        'receipt_id': report.receipt.receipt_id,
        'parents': [
            {
                'receipt_no': parent.receipt_no,
                'issue_id': parent.issue_id,
                'revision_no': parent.origin.revision_no,
            }
            for parent in report.parents
        ],
    }


def run_demo(root: Path, sample: dict) -> None:
    station_path = root / 'station.db'
    issue_path = root / 'issues.db'
    publication_path = root / 'reports.db'
    batch_id = sample['batch_id']
    a_bench, b_bench = sample['benches']
    issuer = 'lichuan-demo'
    with closing(IntakeStore(root / 'intake.db')) as intake:
        with closing(StationStore(station_path)) as station, closing(IssueArchive(issue_path, issuer)) as archive:
            register_batch(station, batch_id, a_bench, b_bench, sample['unit'])
            a_revision = record_revision(station, batch_id, a_bench, sample['a_original'])
            b_revision = record_revision(station, batch_id, b_bench, sample['b_original'])
            a = receive_piece(intake, encode_piece(issue_piece(station, archive, batch_id, a_bench, a_revision)))
            b = receive_piece(intake, encode_piece(issue_piece(station, archive, batch_id, b_bench, b_revision)))
        with closing(PublicationStore(publication_path)) as publisher:
            original = review(intake, publisher, a.receipt_no, b.receipt_no, **sample['request'])
            with closing(StationStore(station_path)) as station, closing(IssueArchive(issue_path, issuer)) as archive:
                revision = record_revision(station, batch_id, a_bench, sample['a_corrected'])
                corrected_piece = issue_piece(station, archive, batch_id, a_bench, revision)
                corrected = receive_piece(intake, encode_piece(corrected_piece))
            updated = review(intake, publisher, corrected.receipt_no, b.receipt_no, **sample['request'])

    expected = {
        'original': {'intervals': [['1/2', '1/2']], 'mse': '4/3'},
        'corrected': {'intervals': [['0', '2']], 'mse': '2'},
    }
    actual = {'original': decision_data(original), 'corrected': decision_data(updated)}
    assert actual == expected, actual
    for report, received in ((original, a), (updated, corrected)):
        assert tuple(parent.receipt_no for parent in report.parents) == (received.receipt_no, b.receipt_no)
        assert tuple(parent.issue_id for parent in report.parents) == (received.piece.issue_id, b.piece.issue_id)
        assert tuple(parent.origin for parent in report.parents) == (received.origin, b.origin)
        assert report.receipt.report_no == report.report_no
    assert original.receipt != updated.receipt

    with closing(PublicationStore(publication_path)) as reopened:
        old_history = get_report(reopened, original.report_no)
        new_history = get_report(reopened, updated.report_no)
    assert old_history == original and new_history == updated
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'v8',
        'input': sample,
        'expected': expected,
        'actual': actual,
        'downstream_expected': [history_data(original), history_data(updated)],
        'downstream_actual': [history_data(old_history), history_data(new_history)],
        'code_paths': [
            'station/revisions.py', 'issue/freeze.py', 'intake/receive.py', 'analysis/request.py',
            'analysis/minima.py', 'publication/storage.py', 'publication/history.py',
        ],
        'oracle': (
            '原版在错峰 0 至 1 秒的覆盖为 2-s，积分为 4(1-s)，覆盖下限将合格域截为 [0,1/2]。'
            '其余窗内覆盖为 1 秒。更正版的覆盖与积分恒为 2 和 4。'
            '双号历史对照首次签发时记录的快照，并各自核对请求指定的父件。'
        ),
    }, ensure_ascii=False, sort_keys=True))


def main() -> None:
    sample_file = Path(__file__).resolve().parent / 'samples' / 'shift.json'
    sample = json.loads(sample_file.read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='lichuan-review-') as directory:
        run_demo(Path(directory), sample)


if __name__ == '__main__':
    main()
