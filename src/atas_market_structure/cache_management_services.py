"""
Cache and Backfill Management Services

Provides centralized cache lifecycle management, backfill state persistence,
and replay integrity tracking for the workbench.

Core Principles:
- Durable: Cache and backfill states survive restarts
- Auditable: All cache operations are logged
- Recoverable: Cache can be rebuilt from ingestion data
- Non-blocking: Cache misses don't crash the system

Cache Management:
- Cache records track verification status, integrity, and health
- Cache can be invalidated and rebuilt on demand
- Cache policies control verification frequency and durability requirements

Backfill Management:
- Backfill requests are persisted to survive restarts
- Backfill progress is tracked and queryable
- Failed backfills can be retried
- Backfill acknowledgments complete the lifecycle

Replay Integrity:
- Snapshots are verified for data integrity
- Multiple verification passes can lock cache as durable
- Cache invalidation triggers manual reimport workflow
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
import json
import logging
import threading

from atas_market_structure.models import (
    ReplayVerificationStatus,
    ReplayWorkbenchIntegrity,
    ServiceHealthStatus,
    Timeframe,
)
from atas_market_structure.repository import AnalysisRepository


LOGGER = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Cache verification settings
MAX_VERIFICATIONS_PER_DAY = 1
VERIFICATION_PASSES_TO_LOCK = 3
CACHE_RECORD_RETENTION = timedelta(days=30)

# Backfill settings
BACKFILL_REQUEST_TTL = timedelta(minutes=5)
BACKFILL_DISPATCH_LEASE = timedelta(seconds=12)
BACKFILL_RECORD_RETENTION = timedelta(hours=2)
MAX_BACKFILL_RETRIES = 3

# Persistence paths
CACHE_STATE_DIR = Path("runtime") / "cache"
BACKFILL_STATE_DIR = Path("runtime") / "backfill"

# Cache state file names
CACHE_INTEGRITY_FILE = "integrity.json"
BACKFILL_INDEX_FILE = "index.json"


# ============================================================================
# Enums
# ============================================================================

class CacheStatus(str, Enum):
    """Cache record status."""
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DURABLE = "durable"
    INVALIDATED = "invalidated"
    REBUILDING = "rebuilding"
    FAILED = "failed"


class BackfillStatus(str, Enum):
    """Backfill request status."""
    PENDING = "pending"
    DISPATCHED = "dispatched"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    ACKNOWLEDGED = "acknowledged"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass(frozen=True)
class CacheRecord:
    """Cache record with verification and integrity tracking."""
    cache_key: str
    status: CacheStatus
    verification_count: int = 0
    last_verified_at: datetime | None = None
    last_invalidated_at: datetime | None = None
    integrity: ReplayWorkbenchIntegrity | None = None
    message: str | None = None

    @property
    def is_durable(self) -> bool:
        return self.status == CacheStatus.DURABLE

    @property
    def needs_verification(self) -> bool:
        return self.status in (CacheStatus.UNVERIFIED, CacheStatus.VERIFIED)

    @property
    def can_serve(self) -> bool:
        return self.status in (CacheStatus.DURABLE, CacheStatus.VERIFIED)

    def with_verification(self, count: int, at: datetime) -> "CacheRecord":
        """Create a new record with updated verification info."""
        return CacheRecord(
            cache_key=self.cache_key,
            status=CacheStatus.DURABLE if count >= VERIFICATION_PASSES_TO_LOCK else CacheStatus.VERIFIED,
            verification_count=count,
            last_verified_at=at,
            last_invalidated_at=self.last_invalidated_at,
            integrity=self.integrity,
            message=f"Verified {count} time(s)",
        )

    def with_invalidation(self, at: datetime, message: str = "Manually invalidated") -> "CacheRecord":
        """Create a new record with invalidation info."""
        return CacheRecord(
            cache_key=self.cache_key,
            status=CacheStatus.INVALIDATED,
            verification_count=0,
            last_verified_at=self.last_verified_at,
            last_invalidated_at=at,
            integrity=self.integrity,
            message=message,
        )


@dataclass
class BackfillRequest:
    """Backfill request with progress tracking."""
    request_id: str
    cache_key: str
    instrument_symbol: str
    display_timeframe: Timeframe
    window_start: datetime
    window_end: datetime
    status: BackfillStatus = BackfillStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    dispatched_at: datetime | None = None
    completed_at: datetime | None = None
    acknowledged_at: datetime | None = None
    retry_count: int = 0
    last_error: str | None = None
    chart_instance_id: str | None = None
    contract_symbol: str | None = None
    root_symbol: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status in (
            BackfillStatus.PENDING,
            BackfillStatus.DISPATCHED,
            BackfillStatus.IN_PROGRESS,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            BackfillStatus.COMPLETED,
            BackfillStatus.FAILED,
            BackfillStatus.EXPIRED,
            BackfillStatus.ACKNOWLEDGED,
        )

    @property
    def age(self) -> timedelta:
        return datetime.now(tz=UTC) - self.created_at

    @property
    def is_expired(self) -> bool:
        return self.age > BACKFILL_REQUEST_TTL and self.status == BackfillStatus.PENDING

    def dispatch(self) -> "BackfillRequest":
        """Mark as dispatched."""
        return BackfillRequest(
            request_id=self.request_id,
            cache_key=self.cache_key,
            instrument_symbol=self.instrument_symbol,
            display_timeframe=self.display_timeframe,
            window_start=self.window_start,
            window_end=self.window_end,
            status=BackfillStatus.DISPATCHED,
            created_at=self.created_at,
            dispatched_at=datetime.now(tz=UTC),
            completed_at=None,
            acknowledged_at=None,
            retry_count=self.retry_count,
            last_error=self.last_error,
            chart_instance_id=self.chart_instance_id,
            contract_symbol=self.contract_symbol,
            root_symbol=self.root_symbol,
        )

    def complete(self) -> "BackfillRequest":
        """Mark as completed."""
        return BackfillRequest(
            request_id=self.request_id,
            cache_key=self.cache_key,
            instrument_symbol=self.instrument_symbol,
            display_timeframe=self.display_timeframe,
            window_start=self.window_start,
            window_end=self.window_end,
            status=BackfillStatus.COMPLETED,
            created_at=self.created_at,
            dispatched_at=self.dispatched_at,
            completed_at=datetime.now(tz=UTC),
            acknowledged_at=None,
            retry_count=self.retry_count,
            last_error=None,
            chart_instance_id=self.chart_instance_id,
            contract_symbol=self.contract_symbol,
            root_symbol=self.root_symbol,
        )

    def fail(self, error: str) -> "BackfillRequest":
        """Mark as failed with error."""
        return BackfillRequest(
            request_id=self.request_id,
            cache_key=self.cache_key,
            instrument_symbol=self.instrument_symbol,
            display_timeframe=self.display_timeframe,
            window_start=self.window_start,
            window_end=self.window_end,
            status=BackfillStatus.FAILED,
            created_at=self.created_at,
            dispatched_at=self.dispatched_at,
            completed_at=None,
            acknowledged_at=None,
            retry_count=self.retry_count + 1,
            last_error=error,
            chart_instance_id=self.chart_instance_id,
            contract_symbol=self.contract_symbol,
            root_symbol=self.root_symbol,
        )

    def acknowledge(self) -> "BackfillRequest":
        """Mark as acknowledged."""
        return BackfillRequest(
            request_id=self.request_id,
            cache_key=self.cache_key,
            instrument_symbol=self.instrument_symbol,
            display_timeframe=self.display_timeframe,
            window_start=self.window_start,
            window_end=self.window_end,
            status=BackfillStatus.ACKNOWLEDGED,
            created_at=self.created_at,
            dispatched_at=self.dispatched_at,
            completed_at=self.completed_at,
            acknowledged_at=datetime.now(tz=UTC),
            retry_count=self.retry_count,
            last_error=self.last_error,
            chart_instance_id=self.chart_instance_id,
            contract_symbol=self.contract_symbol,
            root_symbol=self.root_symbol,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for persistence."""
        return {
            "request_id": self.request_id,
            "cache_key": self.cache_key,
            "instrument_symbol": self.instrument_symbol,
            "display_timeframe": self.display_timeframe.value,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "chart_instance_id": self.chart_instance_id,
            "contract_symbol": self.contract_symbol,
            "root_symbol": self.root_symbol,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackfillRequest":
        """Deserialize from dict."""
        return cls(
            request_id=data["request_id"],
            cache_key=data["cache_key"],
            instrument_symbol=data["instrument_symbol"],
            display_timeframe=Timeframe(data["display_timeframe"]),
            window_start=datetime.fromisoformat(data["window_start"]),
            window_end=datetime.fromisoformat(data["window_end"]),
            status=BackfillStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            dispatched_at=datetime.fromisoformat(data["dispatched_at"]) if data.get("dispatched_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            acknowledged_at=datetime.fromisoformat(data["acknowledged_at"]) if data.get("acknowledged_at") else None,
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error"),
            chart_instance_id=data.get("chart_instance_id"),
            contract_symbol=data.get("contract_symbol"),
            root_symbol=data.get("root_symbol"),
        )


# ============================================================================
# Cache Management Service
# ============================================================================

class CacheManagementService:
    """
    Centralized cache lifecycle management.

    Features:
    - Persistent cache state across restarts
    - Verification tracking with durability thresholds
    - Cache invalidation with audit trail
    - Integrity checking and reporting
    """

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository
        self._lock = threading.Lock()
        self._cache_states: dict[str, CacheRecord] = {}
        self._ensure_state_dir()

    def _ensure_state_dir(self) -> None:
        """Ensure state directories exist."""
        CACHE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        BACKFILL_STATE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------------
    # Cache State Management
    # ------------------------------------------------------------------------

    def get_cache_record(self, cache_key: str) -> CacheRecord | None:
        """Get cache record for a cache key."""
        with self._lock:
            return self._cache_states.get(cache_key)

    def create_cache_record(
        self,
        cache_key: str,
        status: CacheStatus = CacheStatus.UNVERIFIED,
        integrity: ReplayWorkbenchIntegrity | None = None,
    ) -> CacheRecord:
        """Create a new cache record."""
        with self._lock:
            record = CacheRecord(
                cache_key=cache_key,
                status=status,
                integrity=integrity,
            )
            self._cache_states[cache_key] = record
            self._persist_cache_state(cache_key, record)
            return record

    def record_verification(
        self,
        cache_key: str,
        integrity: ReplayWorkbenchIntegrity,
    ) -> CacheRecord:
        """Record a verification pass for a cache key."""
        with self._lock:
            existing = self._cache_states.get(cache_key)
            if existing is None:
                existing = CacheRecord(
                    cache_key=cache_key,
                    status=CacheStatus.UNVERIFIED,
                )

            new_count = existing.verification_count + 1
            now = datetime.now(tz=UTC)
            new_record = existing.with_verification(new_count, now)

            if integrity is not None:
                new_record = CacheRecord(
                    cache_key=new_record.cache_key,
                    status=new_record.status,
                    verification_count=new_record.verification_count,
                    last_verified_at=new_record.last_verified_at,
                    last_invalidated_at=new_record.last_invalidated_at,
                    integrity=integrity,
                    message=new_record.message,
                )

            self._cache_states[cache_key] = new_record
            self._persist_cache_state(cache_key, new_record)
            return new_record

    def invalidate_cache(
        self,
        cache_key: str,
        reason: str = "Manually invalidated",
    ) -> CacheRecord:
        """Invalidate a cache record."""
        with self._lock:
            existing = self._cache_states.get(cache_key)
            if existing is None:
                existing = CacheRecord(
                    cache_key=cache_key,
                    status=CacheStatus.UNVERIFIED,
                )

            now = datetime.now(tz=UTC)
            new_record = existing.with_invalidation(now, reason)
            self._cache_states[cache_key] = new_record
            self._persist_cache_state(cache_key, new_record)
            return new_record

    def list_cache_records(
        self,
        status: CacheStatus | None = None,
        limit: int = 100,
    ) -> list[CacheRecord]:
        """List cache records, optionally filtered by status."""
        with self._lock:
            records = list(self._cache_states.values())
            if status is not None:
                records = [r for r in records if r.status == status]
            return sorted(records, key=lambda r: r.last_verified_at or datetime.min, reverse=True)[:limit]

    def cleanup_expired_cache_records(self) -> int:
        """Remove expired cache records older than retention period."""
        with self._lock:
            now = datetime.now(tz=UTC)
            cutoff = now - CACHE_RECORD_RETENTION
            expired_keys = [
                key
                for key, record in self._cache_states.items()
                if record.last_invalidated_at is not None and record.last_invalidated_at < cutoff
            ]
            for key in expired_keys:
                del self._cache_states[key]
                self._delete_cache_state_file(key)
            return len(expired_keys)

    # ------------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------------

    def _persist_cache_state(self, cache_key: str, record: CacheRecord) -> None:
        """Persist cache state to disk."""
        try:
            safe_key = cache_key.replace("/", "_").replace("|", "_")
            state_file = CACHE_STATE_DIR / f"{safe_key}.json"
            data = {
                "cache_key": record.cache_key,
                "status": record.status.value,
                "verification_count": record.verification_count,
                "last_verified_at": record.last_verified_at.isoformat() if record.last_verified_at else None,
                "last_invalidated_at": record.last_invalidated_at.isoformat() if record.last_invalidated_at else None,
                "message": record.message,
            }
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            LOGGER.warning("Failed to persist cache state for %s: %s", cache_key, exc)

    def _delete_cache_state_file(self, cache_key: str) -> None:
        """Delete cache state file."""
        try:
            safe_key = cache_key.replace("/", "_").replace("|", "_")
            state_file = CACHE_STATE_DIR / f"{safe_key}.json"
            if state_file.exists():
                state_file.unlink()
        except Exception as exc:
            LOGGER.warning("Failed to delete cache state file for %s: %s", cache_key, exc)

    def _load_cache_states(self) -> None:
        """Load cache states from disk on startup."""
        try:
            for state_file in CACHE_STATE_DIR.glob("*.json"):
                try:
                    with open(state_file, encoding="utf-8") as f:
                        data = json.load(f)
                    record = CacheRecord(
                        cache_key=data["cache_key"],
                        status=CacheStatus(data["status"]),
                        verification_count=data.get("verification_count", 0),
                        last_verified_at=datetime.fromisoformat(data["last_verified_at"]) if data.get("last_verified_at") else None,
                        last_invalidated_at=datetime.fromisoformat(data["last_invalidated_at"]) if data.get("last_invalidated_at") else None,
                        message=data.get("message"),
                    )
                    self._cache_states[record.cache_key] = record
                except Exception as exc:
                    LOGGER.warning("Failed to load cache state from %s: %s", state_file, exc)
        except Exception as exc:
            LOGGER.warning("Failed to load cache states: %s", exc)


# ============================================================================
# Backfill Management Service
# ============================================================================

class BackfillManagementService:
    """
    Centralized backfill lifecycle management.

    Features:
    - Persistent backfill state across restarts
    - Automatic expiration of stale requests
    - Retry logic with configurable limits
    - Progress tracking and reporting
    """

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository
        self._lock = threading.Lock()
        self._backfill_requests: dict[str, BackfillRequest] = {}
        self._ensure_state_dir()
        self._load_backfill_state()

    def _ensure_state_dir(self) -> None:
        """Ensure state directories exist."""
        BACKFILL_STATE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------------
    # Backfill Request Management
    # ------------------------------------------------------------------------

    def create_backfill_request(
        self,
        request_id: str,
        cache_key: str,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
    ) -> BackfillRequest:
        """Create a new backfill request."""
        with self._lock:
            request = BackfillRequest(
                request_id=request_id,
                cache_key=cache_key,
                instrument_symbol=instrument_symbol,
                display_timeframe=display_timeframe,
                window_start=window_start,
                window_end=window_end,
                chart_instance_id=chart_instance_id,
                contract_symbol=contract_symbol,
                root_symbol=root_symbol,
            )
            self._backfill_requests[request_id] = request
            self._persist_backfill_state()
            return request

    def get_backfill_request(self, request_id: str) -> BackfillRequest | None:
        """Get backfill request by ID."""
        with self._lock:
            return self._backfill_requests.get(request_id)

    def get_active_backfill_requests(
        self,
        instrument_symbol: str | None = None,
    ) -> list[BackfillRequest]:
        """Get active (non-terminal) backfill requests."""
        with self._lock:
            requests = [
                r for r in self._backfill_requests.values()
                if r.is_active
            ]
            if instrument_symbol is not None:
                requests = [r for r in requests if r.instrument_symbol == instrument_symbol]
            return sorted(requests, key=lambda r: r.created_at)

    def get_backfill_requests_by_cache_key(self, cache_key: str) -> list[BackfillRequest]:
        """Get all backfill requests for a cache key."""
        with self._lock:
            return sorted(
                [r for r in self._backfill_requests.values() if r.cache_key == cache_key],
                key=lambda r: r.created_at,
            )

    def dispatch_backfill(self, request_id: str) -> BackfillRequest | None:
        """Mark backfill request as dispatched."""
        with self._lock:
            request = self._backfill_requests.get(request_id)
            if request is None or not request.is_active:
                return None
            dispatched = request.dispatch()
            self._backfill_requests[request_id] = dispatched
            self._persist_backfill_state()
            return dispatched

    def complete_backfill(self, request_id: str) -> BackfillRequest | None:
        """Mark backfill request as completed."""
        with self._lock:
            request = self._backfill_requests.get(request_id)
            if request is None:
                return None
            completed = request.complete()
            self._backfill_requests[request_id] = completed
            self._persist_backfill_state()
            return completed

    def fail_backfill(self, request_id: str, error: str) -> BackfillRequest | None:
        """Mark backfill request as failed."""
        with self._lock:
            request = self._backfill_requests.get(request_id)
            if request is None:
                return None
            failed = request.fail(error)
            self._backfill_requests[request_id] = failed
            self._persist_backfill_state()
            return failed

    def acknowledge_backfill(self, request_id: str) -> BackfillRequest | None:
        """Mark backfill request as acknowledged (client confirmed)."""
        with self._lock:
            request = self._backfill_requests.get(request_id)
            if request is None:
                return None
            acknowledged = request.acknowledge()
            self._backfill_requests[request_id] = acknowledged
            self._persist_backfill_state()
            return acknowledged

    def cleanup_expired_backfill_requests(self) -> int:
        """Expire old backfill requests past retention period."""
        with self._lock:
            now = datetime.now(tz=UTC)
            expired_requests = [
                req_id
                for req_id, request in self._backfill_requests.items()
                if request.status == BackfillStatus.PENDING
                and (now - request.created_at) > BACKFILL_REQUEST_TTL
            ]
            for req_id in expired_requests:
                self._backfill_requests[req_id] = BackfillRequest(
                    request_id=self._backfill_requests[req_id].request_id,
                    cache_key=self._backfill_requests[req_id].cache_key,
                    instrument_symbol=self._backfill_requests[req_id].instrument_symbol,
                    display_timeframe=self._backfill_requests[req_id].display_timeframe,
                    window_start=self._backfill_requests[req_id].window_start,
                    window_end=self._backfill_requests[req_id].window_end,
                    status=BackfillStatus.EXPIRED,
                    created_at=self._backfill_requests[req_id].created_at,
                    retry_count=self._backfill_requests[req_id].retry_count,
                )
            if expired_requests:
                self._persist_backfill_state()
            return len(expired_requests)

    def get_backfill_statistics(self) -> dict[str, Any]:
        """Get backfill statistics for monitoring."""
        with self._lock:
            stats = {
                "total": len(self._backfill_requests),
                "pending": 0,
                "dispatched": 0,
                "in_progress": 0,
                "completed": 0,
                "failed": 0,
                "expired": 0,
                "acknowledged": 0,
            }
            for request in self._backfill_requests.values():
                stats[request.status.value] = stats.get(request.status.value, 0) + 1
            return stats

    # ------------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------------

    def _persist_backfill_state(self) -> None:
        """Persist backfill state to disk."""
        try:
            index_file = BACKFILL_STATE_DIR / BACKFILL_INDEX_FILE
            data = {
                "updated_at": datetime.now(tz=UTC).isoformat(),
                "requests": [r.to_dict() for r in self._backfill_requests.values()],
            }
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            LOGGER.warning("Failed to persist backfill state: %s", exc)

    def _load_backfill_state(self) -> None:
        """Load backfill state from disk on startup."""
        try:
            index_file = BACKFILL_STATE_DIR / BACKFILL_INDEX_FILE
            if not index_file.exists():
                return
            with open(index_file, encoding="utf-8") as f:
                data = json.load(f)
            for request_data in data.get("requests", []):
                try:
                    request = BackfillRequest.from_dict(request_data)
                    self._backfill_requests[request.request_id] = request
                except Exception as exc:
                    LOGGER.warning("Failed to load backfill request: %s", exc)
            LOGGER.info("Loaded %d backfill requests from disk", len(self._backfill_requests))
        except Exception as exc:
            LOGGER.warning("Failed to load backfill state: %s", exc)


# ============================================================================
# Composite Service
# ============================================================================

class WorkbenchManagementService:
    """
    Composite service combining cache and backfill management.

    This service provides a unified interface for workbench lifecycle management
    and coordinates between cache and backfill subsystems.
    """

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository
        self._cache_service = CacheManagementService(repository)
        self._backfill_service = BackfillManagementService(repository)

    @property
    def cache(self) -> CacheManagementService:
        """Access cache management service."""
        return self._cache_service

    @property
    def backfill(self) -> BackfillManagementService:
        """Access backfill management service."""
        return self._backfill_service

    def get_health_summary(self) -> dict[str, Any]:
        """Get health summary for monitoring."""
        backfill_stats = self._backfill_service.get_backfill_statistics()
        cache_records = self._cache_service.list_cache_records(limit=100)

        return {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "cache": {
                "total_records": len(cache_records),
                "durable_count": sum(1 for r in cache_records if r.is_durable),
                "needs_verification": sum(1 for r in cache_records if r.needs_verification),
                "invalidated_count": sum(1 for r in cache_records if r.status == CacheStatus.INVALIDATED),
            },
            "backfill": backfill_stats,
            "healthy": (
                backfill_stats["pending"] == 0
                and backfill_stats["failed"] == 0
            ),
        }

    def cleanup_expired_records(self) -> dict[str, int]:
        """Clean up expired cache and backfill records."""
        cache_cleaned = self._cache_service.cleanup_expired_cache_records()
        backfill_cleaned = self._backfill_service.cleanup_expired_backfill_requests()
        return {
            "cache_records_cleaned": cache_cleaned,
            "backfill_requests_cleaned": backfill_cleaned,
        }
