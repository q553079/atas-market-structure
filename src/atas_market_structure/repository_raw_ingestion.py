from __future__ import annotations

from datetime import datetime
from typing import Protocol

from atas_market_structure.repository_records import (
    StoredAnalysis,
    StoredIngestion,
    StoredIngestionDeadLetter,
    StoredIngestionIdempotencyKey,
    StoredIngestionRunLog,
)


class RawIngestionRepository(Protocol):
    """Append-only ingestion and operational reliability surface.

    Allowed to own:
    raw payload persistence, idempotency keys, dead letters, ingestion run logs.

    Must not own:
    recognition belief/episode state, tuning lineage, chat session state.
    """

    def save_ingestion(
        self,
        *,
        ingestion_id: str,
        ingestion_kind: str,
        source_snapshot_id: str,
        instrument_symbol: str,
        observed_payload: dict[str, object],
        stored_at: datetime,
    ) -> StoredIngestion:
        ...

    def get_ingestion(self, ingestion_id: str) -> StoredIngestion | None:
        ...

    def update_ingestion_observed_payload(
        self,
        *,
        ingestion_id: str,
        observed_payload: dict[str, object],
    ) -> StoredIngestion | None:
        ...

    def list_ingestions(
        self,
        *,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        source_snapshot_id: str | None = None,
        limit: int = 100,
        stored_at_after: datetime | None = None,
        stored_at_before: datetime | None = None,
    ) -> list[StoredIngestion]:
        ...

    def purge_ingestions(
        self,
        *,
        ingestion_kinds: list[str],
        instrument_symbol: str | None,
        cutoff: datetime,
    ) -> int:
        ...

    def save_analysis(
        self,
        *,
        analysis_id: str,
        ingestion_id: str,
        route_key: str,
        analysis_payload: dict[str, object],
        stored_at: datetime,
    ) -> StoredAnalysis:
        ...

    def get_analysis(self, analysis_id: str) -> StoredAnalysis | None:
        ...

    def save_dead_letter(
        self,
        *,
        dead_letter_id: str,
        endpoint: str,
        ingestion_kind: str,
        instrument_symbol: str | None,
        source_snapshot_id: str | None,
        request_id: str | None,
        dedup_key: str,
        payload_hash: str,
        raw_payload: str,
        error_code: str,
        error_detail: dict[str, object],
        ingestion_id: str | None,
        stored_at: datetime,
    ) -> StoredIngestionDeadLetter:
        ...

    def list_dead_letters(
        self,
        *,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        limit: int = 100,
    ) -> list[StoredIngestionDeadLetter]:
        ...

    def get_ingestion_idempotency_key(self, endpoint: str, dedup_key: str) -> StoredIngestionIdempotencyKey | None:
        ...

    def save_ingestion_idempotency_key(
        self,
        *,
        endpoint: str,
        dedup_key: str,
        request_id: str | None,
        payload_hash: str,
        ingestion_id: str,
        response_payload: dict[str, object],
        first_seen_at: datetime,
        last_seen_at: datetime,
        duplicate_count: int,
    ) -> StoredIngestionIdempotencyKey:
        ...

    def touch_ingestion_idempotency_key(
        self,
        endpoint: str,
        dedup_key: str,
        *,
        last_seen_at: datetime,
        duplicate_count: int,
    ) -> StoredIngestionIdempotencyKey | None:
        ...

    def save_ingestion_run_log(
        self,
        *,
        run_id: str,
        endpoint: str,
        ingestion_kind: str,
        instrument_symbol: str | None,
        request_id: str | None,
        dedup_key: str,
        payload_hash: str,
        outcome: str,
        http_status: int,
        ingestion_id: str | None,
        dead_letter_id: str | None,
        detail: dict[str, object],
        started_at: datetime,
        completed_at: datetime,
    ) -> StoredIngestionRunLog:
        ...

    def list_ingestion_run_logs(
        self,
        *,
        endpoint: str | None = None,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        limit: int = 100,
    ) -> list[StoredIngestionRunLog]:
        ...
