from dataclasses import dataclass

from station.observations import require_number


@dataclass(frozen=True)
class SuccessReceipt:
    receipt_id: str
    report_no: int


def make_success_receipt(report_no: int) -> SuccessReceipt:
    require_number(report_no, 'report number')
    return SuccessReceipt(f'success-{report_no}', report_no)
