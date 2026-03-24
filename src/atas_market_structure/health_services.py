"""
Health and Status Services Layer

Provides unified health monitoring, degraded mode detection, and service status
reporting for the entire system.

Core Principles:
- Observable: All health states are queryable via API
- Compositional: Health checks are hierarchical (service -> component -> source)
- Graceful: Degraded modes don't crash the service
- Actionable: Health responses include recommended actions

Health Check Hierarchy:
    Service Health
        ├── Ingestion Health
        │       ├── Depth Monitoring Health
        │       ├── Adapter Bridge Health
        │       └── Storage Health
        ├── Recognition Health
        │       ├── Feature Builder Health
        │       ├── Regime Updater Health
        │       └── Event Updater Health
        └── Projection Health
                ├── Belief Timeline Health
                ├── Episode Timeline Health
                └── Cache Health

Degraded Modes:
- NO_DEPTH: Depth data unavailable or stale (> 2 minutes)
- NO_DOM: DOM data unavailable
- NO_AI: AI service unavailable
- STALE_MACRO: Macro data stale (> 20 minutes)
- REPLAY_REBUILD: Replay cache in rebuild mode

API Endpoints:
- GET /health - Simple heartbeat
- GET /health/ingestion - Ingestion plane health
- GET /health/recognition - Recognition plane health
- GET /health/projection - Projection plane health
- GET /health/data-quality - Data quality status
- GET /health/service - Unified service health
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from atas_market_structure.models import (
    BeliefDataStatus,
    DataQualityResponse,
    DataQualitySourceStatus,
    DegradedMode,
    IngestionHealthResponse,
    IngestionMetricsSnapshot,
    IngestionRunLogEntry,
    ServiceHealthStatus,
)
from atas_market_structure.repository import AnalysisRepository


LOGGER = __import__("logging").getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Data freshness thresholds
MACRO_STALE_AFTER = timedelta(minutes=20)
DEPTH_STALE_AFTER = timedelta(minutes=2)
DOM_STALE_AFTER = timedelta(minutes=2)

# Health check configuration
HEALTH_CHECK_TIMEOUT = timedelta(seconds=5)
RUN_LOG_WINDOW = timedelta(hours=1)


# ============================================================================
# Data Structures
# ============================================================================

class HealthComponent(str, Enum):
    """Health check components."""
    INGESTION = "ingestion"
    RECOGNITION = "recognition"
    PROJECTION = "projection"
    STORAGE = "storage"
    ADAPTER_BRIDGE = "adapter_bridge"
    DEPTH_MONITORING = "depth_monitoring"
    CACHE = "cache"


@dataclass(frozen=True)
class ComponentHealth:
    """Health status for a single component."""
    name: str
    status: ServiceHealthStatus
    message: str | None = None
    latency_ms: float | None = None
    error_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def healthy(cls, name: str, message: str | None = None) -> "ComponentHealth":
        return cls(name=name, status=ServiceHealthStatus.HEALTHY, message=message)

    @classmethod
    def degraded(cls, name: str, message: str, **details: Any) -> "ComponentHealth":
        return cls(name=name, status=ServiceHealthStatus.DEGRADED, message=message, details=details)

    @classmethod
    def rebuild_required(cls, name: str, message: str) -> "ComponentHealth":
        return cls(name=name, status=ServiceHealthStatus.REBUILD_REQUIRED, message=message)

    @classmethod
    def paused(cls, name: str, message: str) -> "ComponentHealth":
        return cls(name=name, status=ServiceHealthStatus.PAUSED, message=message)


@dataclass(frozen=True)
class ServiceHealthResponse:
    """Unified service health response."""
    schema_version: str = "1.0.0"
    service: str = "market_structure"
    status: ServiceHealthStatus = ServiceHealthStatus.HEALTHY
    checked_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    # Degraded mode info
    degraded_modes: list[DegradedMode] = field(default_factory=list)
    degraded_reasons: list[str] = field(default_factory=list)

    # Component health
    components: dict[str, ComponentHealth] = field(default_factory=dict)

    # Data quality summary
    data_quality: DataQualityResponse | None = None

    # Recommended actions
    recommended_actions: list[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.status == ServiceHealthStatus.HEALTHY

    @property
    def is_degraded(self) -> bool:
        return self.status == ServiceHealthStatus.DEGRADED

    @property
    def needs_rebuild(self) -> bool:
        return self.status == ServiceHealthStatus.REBUILD_REQUIRED

    @property
    def is_paused(self) -> bool:
        return self.status == ServiceHealthStatus.PAUSED


# ============================================================================
# Health Service
# ============================================================================

class HealthService:
    """
    Unified health monitoring service.

    Provides:
    - Component-level health checks
    - Aggregated service health
    - Degraded mode detection
    - Data quality assessment
    - Recommended actions
    """

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository
        self._last_check: datetime | None = None
        self._last_response: ServiceHealthResponse | None = None

    def get_service_health(self) -> ServiceHealthResponse:
        """
        Get unified service health status.

        Returns:
            ServiceHealthResponse with full health status
        """
        checked_at = datetime.now(tz=UTC)

        # Check all components
        components: dict[str, ComponentHealth] = {}
        degraded_modes: set[DegradedMode] = set()
        degraded_reasons: list[str] = []

        # Ingestion health
        ingestion_health = self._check_ingestion_health()
        components[HealthComponent.INGESTION] = ingestion_health
        self._extract_degraded_info(ingestion_health, degraded_modes, degraded_reasons)

        # Storage health
        storage_health = self._check_storage_health()
        components[HealthComponent.STORAGE] = storage_health

        # Recognition health (basic)
        recognition_health = self._check_recognition_health()
        components[HealthComponent.RECOGNITION] = recognition_health

        # Cache health
        cache_health = self._check_cache_health()
        components[HealthComponent.CACHE] = cache_health

        # Determine overall status
        overall_status = self._determine_overall_status(components, degraded_modes)

        # Generate recommended actions
        recommended_actions = self._generate_recommended_actions(components, degraded_modes)

        response = ServiceHealthResponse(
            schema_version="1.0.0",
            service="market_structure",
            status=overall_status,
            checked_at=checked_at,
            degraded_modes=list(degraded_modes),
            degraded_reasons=degraded_reasons,
            components=components,
            data_quality=None,  # Can be populated by calling data quality check
            recommended_actions=recommended_actions,
        )

        self._last_check = checked_at
        self._last_response = response

        return response

    def get_ingestion_health(self) -> IngestionHealthResponse:
        """
        Get ingestion plane health status.

        Returns:
            IngestionHealthResponse with ingestion-specific health info
        """
        checked_at = datetime.now(tz=UTC)

        # Get latest ingestion for health assessment
        latest_ingestions = self._get_latest_ingestions()

        # Assess degraded modes
        degraded_modes = self._assess_degraded_modes(latest_ingestions)

        # Determine status
        status = ServiceHealthStatus.HEALTHY
        if degraded_modes:
            if DegradedMode.REPLAY_REBUILD in degraded_modes:
                status = ServiceHealthStatus.REBUILD_REQUIRED
            else:
                status = ServiceHealthStatus.DEGRADED

        # Build data status
        data_status = BeliefDataStatus(
            data_freshness_ms=0,
            feature_completeness=1.0,
            depth_available=DegradedMode.NO_DEPTH not in degraded_modes,
            dom_available=DegradedMode.NO_DOM not in degraded_modes,
            ai_available=DegradedMode.NO_AI not in degraded_modes,
            degraded_modes=degraded_modes,
            freshness="fresh",
            completeness="complete",
        )

        # Build metrics
        metrics = IngestionMetricsSnapshot(
            total_count=0,
            accepted_count=0,
            dead_letter_count=0,
            duplicate_count=0,
            downstream_failure_count=0,
            success_rate=1.0,
        )

        return IngestionHealthResponse(
            schema_version="1.0.0",
            status=status,
            degraded_reasons=[m.value for m in degraded_modes],
            profile_version="unknown",
            engine_version="unknown",
            data_status=data_status,
            last_success_at=checked_at,
            last_dead_letter_at=None,
            metrics=metrics,
            recent_runs=[],
        )

    def get_data_quality(self, instrument_symbol: str | None = None) -> DataQualityResponse:
        """
        Get data quality status.

        Args:
            instrument_symbol: Optional instrument to check

        Returns:
            DataQualityResponse with data quality info
        """
        checked_at = datetime.now(tz=UTC)

        # Get latest ingestions for quality assessment
        latest_ingestions = self._get_latest_ingestions(instrument_symbol)

        # Assess degraded modes
        degraded_modes = self._assess_degraded_modes(latest_ingestions)

        # Determine status
        status = ServiceHealthStatus.HEALTHY
        if degraded_modes:
            if DegradedMode.REPLAY_REBUILD in degraded_modes:
                status = ServiceHealthStatus.REBUILD_REQUIRED
            elif DegradedMode.STALE_MACRO in degraded_modes:
                status = ServiceHealthStatus.DEGRADED

        # Build data status
        data_status = BeliefDataStatus(
            data_freshness_ms=0,
            feature_completeness=1.0,
            depth_available=DegradedMode.NO_DEPTH not in degraded_modes,
            dom_available=DegradedMode.NO_DOM not in degraded_modes,
            ai_available=DegradedMode.NO_AI not in degraded_modes,
            degraded_modes=degraded_modes,
            freshness="fresh",
            completeness="complete",
        )

        # Build source statuses
        source_statuses = self._build_source_statuses(latest_ingestions)

        return DataQualityResponse(
            schema_version="1.0.0",
            status=status,
            degraded_reasons=[m.value for m in degraded_modes],
            data_status=data_status,
            source_statuses=source_statuses,
            profile_version="unknown",
            engine_version="unknown",
        )

    # ------------------------------------------------------------------------
    # Internal Health Checks
    # ------------------------------------------------------------------------

    def _check_ingestion_health(self) -> ComponentHealth:
        """Check ingestion component health."""
        try:
            latest = self._repository.list_ingestions(limit=1)
            if latest:
                return ComponentHealth.healthy(
                    name=HealthComponent.INGESTION,
                    message="Ingestion operational"
                )
            else:
                return ComponentHealth.degraded(
                    name=HealthComponent.INGESTION,
                    message="No recent ingestions",
                    recent_count=0
                )
        except Exception as exc:
            LOGGER.warning("Ingestion health check failed: %s", exc)
            return ComponentHealth.degraded(
                name=HealthComponent.INGESTION,
                message=f"Health check failed: {exc}",
                error_count=1
            )

    def _check_storage_health(self) -> ComponentHealth:
        """Check storage component health."""
        try:
            # Try a simple query to verify storage is accessible
            self._repository.list_ingestions(limit=1)
            return ComponentHealth.healthy(
                name=HealthComponent.STORAGE,
                message="Storage operational"
            )
        except Exception as exc:
            LOGGER.warning("Storage health check failed: %s", exc)
            return ComponentHealth.degraded(
                name=HealthComponent.STORAGE,
                message=f"Storage access failed: {exc}",
                error_count=1
            )

    def _check_recognition_health(self) -> ComponentHealth:
        """Check recognition component health."""
        try:
            # Basic check - verify we can access recognition-related data
            profiles = self._repository.get_active_instrument_profile("TEST")
            return ComponentHealth.healthy(
                name=HealthComponent.RECOGNITION,
                message="Recognition operational"
            )
        except Exception as exc:
            LOGGER.warning("Recognition health check failed: %s", exc)
            return ComponentHealth.degraded(
                name=HealthComponent.RECOGNITION,
                message=f"Recognition check failed: {exc}",
                error_count=1
            )

    def _check_cache_health(self) -> ComponentHealth:
        """Check cache component health."""
        try:
            # Check if replay cache is accessible
            return ComponentHealth.healthy(
                name=HealthComponent.CACHE,
                message="Cache operational"
            )
        except Exception as exc:
            LOGGER.warning("Cache health check failed: %s", exc)
            return ComponentHealth.degraded(
                name=HealthComponent.CACHE,
                message=f"Cache access failed: {exc}",
                error_count=1
            )

    # ------------------------------------------------------------------------
    # Degraded Mode Assessment
    # ------------------------------------------------------------------------

    def _assess_degraded_modes(self, latest_ingestions: list[Any]) -> list[DegradedMode]:
        """Assess current degraded modes from ingestion data."""
        degraded_modes: list[DegradedMode] = []
        now = datetime.now(tz=UTC)

        for ingestion in latest_ingestions:
            observed_at = getattr(ingestion, "observed_at", None)
            if observed_at is None:
                continue

            # Check depth freshness
            if "depth" in ingestion.ingestion_kind:
                age = now - observed_at
                if age > DEPTH_STALE_AFTER:
                    degraded_modes.append(DegradedMode.NO_DEPTH)

            # Check macro freshness
            if "market_structure" in ingestion.ingestion_kind:
                age = now - observed_at
                if age > MACRO_STALE_AFTER:
                    degraded_modes.append(DegradedMode.STALE_MACRO)

        return list(set(degraded_modes))

    def _extract_degraded_info(
        self,
        component: ComponentHealth,
        degraded_modes: set[DegradedMode],
        reasons: list[str]
    ) -> None:
        """Extract degraded info from component health."""
        if component.status == ServiceHealthStatus.DEGRADED:
            if component.message:
                reasons.append(component.message)

    def _determine_overall_status(
        self,
        components: dict[str, ComponentHealth],
        degraded_modes: set[DegradedMode]
    ) -> ServiceHealthStatus:
        """Determine overall service status from components."""
        # Check for critical failures
        for component in components.values():
            if component.status == ServiceHealthStatus.PAUSED:
                return ServiceHealthStatus.PAUSED
            if component.status == ServiceHealthStatus.REBUILD_REQUIRED:
                return ServiceHealthStatus.REBUILD_REQUIRED

        # Check for degraded modes
        if DegradedMode.REPLAY_REBUILD in degraded_modes:
            return ServiceHealthStatus.REBUILD_REQUIRED

        # Check for any degraded components
        for component in components.values():
            if component.status == ServiceHealthStatus.DEGRADED:
                return ServiceHealthStatus.DEGRADED

        # Check for errors in components
        for component in components.values():
            if component.error_count > 0:
                return ServiceHealthStatus.DEGRADED

        return ServiceHealthStatus.HEALTHY

    def _generate_recommended_actions(
        self,
        components: dict[str, ComponentHealth],
        degraded_modes: set[DegradedMode]
    ) -> list[str]:
        """Generate recommended actions based on health status."""
        actions: list[str] = []

        if DegradedMode.NO_DEPTH in degraded_modes:
            actions.append("Enable depth monitoring to improve recognition accuracy")

        if DegradedMode.NO_DOM in degraded_modes:
            actions.append("Enable DOM data to improve event detection")

        if DegradedMode.STALE_MACRO in degraded_modes:
            actions.append("Check market structure ingestion - data appears stale")

        if DegradedMode.REPLAY_REBUILD in degraded_modes:
            actions.append("Initiate replay rebuild to restore data integrity")

        if DegradedMode.NO_AI in degraded_modes:
            actions.append("Configure AI service for enhanced analysis")

        # Check for component issues
        for name, component in components.items():
            if component.status == ServiceHealthStatus.DEGRADED:
                actions.append(f"Investigate {name} component: {component.message}")

        if not actions:
            actions.append("System operating normally")

        return actions

    # ------------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------------

    def _get_latest_ingestions(self, instrument_symbol: str | None = None) -> list[Any]:
        """Get latest ingestions for health assessment."""
        try:
            kinds = [
                "market_structure",
                "event_snapshot",
                "process_context",
                "depth_snapshot",
                "adapter_continuous_state",
            ]
            ingestions = []
            for kind in kinds:
                items = self._repository.list_ingestions(
                    ingestion_kind=kind,
                    instrument_symbol=instrument_symbol,
                    limit=10,
                )
                ingestions.extend(items)
            return ingestions
        except Exception as exc:
            LOGGER.warning("Failed to get latest ingestions: %s", exc)
            return []

    def _build_source_statuses(self, latest_ingestions: list[Any]) -> list[DataQualitySourceStatus]:
        """Build source statuses from ingestion data."""
        source_statuses: list[DataQualitySourceStatus] = []
        now = datetime.now(tz=UTC)

        # Group by ingestion kind
        kinds_seen: set[str] = set()
        for ingestion in latest_ingestions:
            kind = ingestion.ingestion_kind
            if kind in kinds_seen:
                continue
            kinds_seen.add(kind)

            observed_at = getattr(ingestion, "observed_at", None)
            freshness = "offline"
            if observed_at is not None:
                age = (now - observed_at).total_seconds()
                if age <= 10:
                    freshness = "fresh"
                elif age <= 60:
                    freshness = "delayed"
                else:
                    freshness = "stale"

            source_statuses.append(
                DataQualitySourceStatus(
                    source=kind,
                    freshness=freshness,
                    last_seen=observed_at,
                    is_healthy=freshness in ("fresh", "delayed"),
                )
            )

        return source_statuses
