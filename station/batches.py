from dataclasses import dataclass

from station.observations import require_text
from station.storage import StationStore


@dataclass(frozen=True)
class BatchDefinition:
    batch_id: str
    a_bench: str
    b_bench: str
    unit: str

    def role_of(self, bench_id: str) -> str:
        if bench_id == self.a_bench:
            return 'A'
        if bench_id == self.b_bench:
            return 'B'
        raise ValueError(f'bench {bench_id!r} does not belong to batch {self.batch_id!r}')


def register_batch(
    store: StationStore, batch_id: str, a_bench: str, b_bench: str, unit: str,
) -> str:
    definition = (
        require_text(batch_id, 'batch id'),
        require_text(a_bench, 'A bench'),
        require_text(b_bench, 'B bench'),
        require_text(unit, 'reading unit'),
    )
    if a_bench == b_bench:
        raise ValueError('a batch requires two distinct benches')
    if store.write_batch(*definition) != definition:
        raise ValueError(f'conflicting definition for batch {batch_id!r}')
    return batch_id


def load_batch(store: StationStore, batch_id: str) -> BatchDefinition:
    require_text(batch_id, 'batch id')
    row = store.read_batch(batch_id)
    if row is None:
        raise LookupError(f'unknown batch {batch_id!r}')
    return BatchDefinition(*row)
