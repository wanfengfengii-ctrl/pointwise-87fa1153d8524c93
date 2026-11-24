from dataclasses import dataclass
from typing import Iterable

from station.batches import BatchDefinition, load_batch
from station.observations import (
    Observation, ObservationInput, normalize_observations, require_number, require_text,
)
from station.storage import StationStore


@dataclass(frozen=True)
class Revision:
    revision_no: int
    batch: BatchDefinition
    bench_id: str
    role: str
    observations: tuple[Observation, ...]


def record_revision(
    store: StationStore,
    batch_id: str,
    bench_id: str,
    rows: Iterable[ObservationInput | Observation],
) -> int:
    batch = load_batch(store, batch_id)
    require_text(bench_id, 'bench id')
    batch.role_of(bench_id)
    observations = normalize_observations(rows)
    return store.save_revision(batch_id, bench_id, observations)


def load_revision(
    store: StationStore, batch_id: str, bench_id: str, revision_no: int,
) -> Revision:
    batch = load_batch(store, batch_id)
    require_text(bench_id, 'bench id')
    role = batch.role_of(bench_id)
    require_number(revision_no, 'revision number')
    observations = store.read_revision(batch_id, bench_id, revision_no)
    if observations is None:
        raise LookupError(f'unknown revision {revision_no} for batch {batch_id!r}, bench {bench_id!r}')
    return Revision(revision_no, batch, bench_id, role, observations)
