from analysis.minima import ReviewDecision
from analysis.request import ReviewRequest
from intake.selection import ReviewPair
from publication.lineage import snapshot_parents
from publication.storage import PublicationStore, ReportRecord


def finalize_report(
    store: PublicationStore,
    request: ReviewRequest,
    decision: ReviewDecision,
    pair: ReviewPair,
) -> ReportRecord:
    return store.commit_report(request, decision, snapshot_parents(pair))
