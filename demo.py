import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.request import review, review_switch
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


def switch_data(report: ReportRecord) -> dict:
    decision = report.decision
    return {
        'regions': [
            [[str(x), str(y)] for x, y in region.vertices] for region in decision.regions
        ],
        'mse': None if decision.minimum_mse is None else str(decision.minimum_mse),
    }


def history_data(report: ReportRecord) -> dict:
    return {
        'report_no': report.report_no,
        'decision': switch_data(report) if hasattr(report.decision, 'regions') else decision_data(report),
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


def run_demo(root: Path, sample: dict, switch_sample: dict) -> None:
    station_path = root / 'station.db'
    issue_path = root / 'issues.db'
    publication_path = root / 'reports.db'
    batch_id = sample['batch_id']
    a_bench, b_bench = sample['benches']
    issuer = 'lichuan-demo'
    switch_case = next(
        case for case in switch_sample['cases'] if case['batch_id'] == 'LC-switch-limit'
    )
    intake = IntakeStore(root / 'intake.db')
    try:
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
            with closing(StationStore(station_path)) as station, closing(IssueArchive(issue_path, issuer)) as archive:
                register_batch(
                    station, switch_case['batch_id'], a_bench, b_bench, switch_sample['unit'],
                )
                switch_a_revision = record_revision(
                    station, switch_case['batch_id'], a_bench, switch_case['a_rows'],
                )
                switch_b_revision = record_revision(
                    station, switch_case['batch_id'], b_bench, switch_case['b_rows'],
                )
                switch_a = receive_piece(intake, encode_piece(issue_piece(
                    station, archive, switch_case['batch_id'], a_bench, switch_a_revision,
                )))
                switch_b = receive_piece(intake, encode_piece(issue_piece(
                    station, archive, switch_case['batch_id'], b_bench, switch_b_revision,
                )))
            request = switch_case['request']
            switched = review_switch(
                intake,
                publisher,
                switch_a.receipt_no,
                switch_b.receipt_no,
                request['cut'],
                request['before_window'],
                request['after_window'],
                request['max_change'],
                request['minimum_coverage'],
            )
        intake.close()

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

        switched_expected = {
            'mse': '1',
            'regions': [[['0', '1/2'], ['1/2', '1']]],
        }
        assert switch_data(switched) == switched_expected, switch_data(switched)
        assert tuple(parent.receipt_no for parent in switched.parents) == (
            switch_a.receipt_no, switch_b.receipt_no,
        )
        assert tuple(parent.issue_id for parent in switched.parents) == (
            switch_a.piece.issue_id, switch_b.piece.issue_id,
        )
        assert tuple(parent.origin for parent in switched.parents) == (
            switch_a.origin, switch_b.origin,
        )
        # The over-limit pair lies outside the allowed switch change of one half second.
        assert switched.decision.contains('1/4', '3/4')
        assert not switched.decision.contains(0, 1)
        assert not switched.decision.contains(0, 0)
        assert switched.receipt.report_no == switched.report_no

        with closing(PublicationStore(publication_path)) as reopened:
            old_history = get_report(reopened, original.report_no)
            new_history = get_report(reopened, updated.report_no)
            switch_history = get_report(reopened, switched.report_no)
        assert old_history == original and new_history == updated
        assert switch_history == switched
        assert switch_history.decision.contains('1/4', '3/4')
    finally:
        intake.close()

    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'v8',
        'input': sample,
        'expected': expected,
        'actual': actual,
        'downstream_expected': [history_data(original), history_data(updated)],
        'downstream_actual': [history_data(old_history), history_data(new_history)],
        'switch': {
            'case': switch_case,
            'expected': switched_expected,
            'actual': switch_data(switched),
            'downstream_expected': history_data(switched),
            'downstream_actual': history_data(switch_history),
        },
        'code_paths': [
            'station/revisions.py', 'issue/freeze.py', 'intake/receive.py', 'analysis/request.py',
            'analysis/minima.py', 'analysis/switch.py', 'analysis/convex.py',
            'publication/storage.py', 'publication/history.py',
        ],
        'oracle': (
            '原版在错峰 0 至 1 秒的覆盖为 2-s，积分为 4(1-s)，覆盖下限将合格域截为 [0,1/2]。'
            '其余窗内覆盖为 1 秒。更正版的覆盖与积分恒为 2 和 4。'
            '换档样例在切点 1 秒处把乙台分成前后两段：前档 s1 决定 0 至 1 秒段，后档 s2 决定 1 至 2 秒段，'
            '受 0 <= s2 - s1 <= 1/2 约束，最优为线段 s2 = s1 + 1/2，均方差为 1，'
            '故 (1/4, 3/4) 入集而超幅对 (0, 1) 不入集。'
            '关实收库后重开发布库，按原号领回原版、更正版与换档三份完整裁决和出处。'
        ),
    }, ensure_ascii=False, sort_keys=True))


def main() -> None:
    root = Path(__file__).resolve().parent
    sample = json.loads((root / 'samples' / 'shift.json').read_text(encoding='utf-8'))
    switch_sample = json.loads((root / 'samples' / 'switch.json').read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='lichuan-review-') as directory:
        run_demo(Path(directory), sample, switch_sample)


if __name__ == '__main__':
    main()
