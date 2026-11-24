from publication.storage import PublicationStore, ReportRecord
from station.observations import require_number


def get_report(store: PublicationStore, report_no: int) -> ReportRecord | None:
    require_number(report_no, 'report number')
    return store.load_report(report_no)
