from issue.archive import IssueArchive
from issue.envelope import FrozenPiece, PieceOrigin
from issue.support import project_support
from station.revisions import load_revision
from station.storage import StationStore


def issue_piece(
    station: StationStore,
    archive: IssueArchive,
    batch_id: str,
    bench_id: str,
    revision_no: int,
) -> FrozenPiece:
    revision = load_revision(station, batch_id, bench_id, revision_no)
    origin = PieceOrigin(
        revision.batch.batch_id,
        revision.bench_id,
        revision.role,
        revision.batch.unit,
        revision.revision_no,
    )
    return archive.save_piece(origin, project_support(revision.observations))
