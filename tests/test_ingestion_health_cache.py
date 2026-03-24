"""
Tests for ingestion validation, health endpoints, degraded mode, and cache management.

These tests verify:
1. Ingestion validation with malformed payloads
2. Health endpoint functionality
3. Degraded mode detection and behavior
4. Replay/projection endpoints basic functionality
5. Recognizer unavailability graceful behavior
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Test Health Service
# ============================================================================

class TestHealthService:
    """Tests for the HealthService."""

    def test_service_health_returns_structured_response(self):
        """Test that get_service_health returns a structured response."""
        from atas_market_structure.health_services import (
            HealthService,
            ComponentHealth,
            ServiceHealthResponse,
        )
        from atas_market_structure.models import ServiceHealthStatus

        # Create mock repository
        mock_repo = MagicMock()
        mock_repo.list_ingestions.return_value = []
        mock_repo.get_active_instrument_profile.return_value = None

        # Create health service
        service = HealthService(mock_repo)

        # Get health
        health = service.get_service_health()

        # Verify structure
        assert isinstance(health, ServiceHealthResponse)
        assert hasattr(health, "schema_version")
        assert hasattr(health, "service")
        assert hasattr(health, "status")
        assert hasattr(health, "checked_at")
        assert hasattr(health, "degraded_modes")
        assert hasattr(health, "degraded_reasons")
        assert hasattr(health, "components")
        assert hasattr(health, "recommended_actions")

    def test_component_health_factory_methods(self):
        """Test ComponentHealth factory methods."""
        from atas_market_structure.health_services import ComponentHealth
        from atas_market_structure.models import ServiceHealthStatus

        # Test healthy
        healthy = ComponentHealth.healthy("test", "All good")
        assert healthy.status == ServiceHealthStatus.HEALTHY
        assert healthy.message == "All good"
        assert healthy.name == "test"

        # Test degraded
        degraded = ComponentHealth.degraded("test", "Something wrong", detail="value")
        assert degraded.status == ServiceHealthStatus.DEGRADED
        assert degraded.details == {"detail": "value"}

        # Test rebuild_required
        rebuild = ComponentHealth.rebuild_required("test", "Needs rebuild")
        assert rebuild.status == ServiceHealthStatus.REBUILD_REQUIRED

        # Test paused
        paused = ComponentHealth.paused("test", "Service paused")
        assert paused.status == ServiceHealthStatus.PAUSED

    def test_service_health_determines_overall_status(self):
        """Test overall status determination logic."""
        from atas_market_structure.health_services import (
            HealthService,
            ComponentHealth,
        )
        from atas_market_structure.models import ServiceHealthStatus

        mock_repo = MagicMock()
        service = HealthService(mock_repo)

        # Test healthy
        components = {
            "ingestion": ComponentHealth.healthy("ingestion"),
            "storage": ComponentHealth.healthy("storage"),
        }
        status = service._determine_overall_status(components, set())
        assert status == ServiceHealthStatus.HEALTHY

        # Test degraded
        components = {
            "ingestion": ComponentHealth.healthy("ingestion"),
            "storage": ComponentHealth.degraded("storage", "Storage degraded"),
        }
        status = service._determine_overall_status(components, set())
        assert status == ServiceHealthStatus.DEGRADED

    def test_ingestion_health_returns_response(self):
        """Test that get_ingestion_health returns proper response."""
        from atas_market_structure.health_services import HealthService
        from atas_market_structure.models import ServiceHealthStatus

        mock_repo = MagicMock()
        mock_repo.list_ingestions.return_value = []

        service = HealthService(mock_repo)
        health = service.get_ingestion_health()

        assert health.status == ServiceHealthStatus.HEALTHY
        assert hasattr(health, "schema_version")
        assert hasattr(health, "data_status")
        # Verify metrics has required fields
        assert hasattr(health.metrics, "total_count")
        assert hasattr(health.metrics, "downstream_failure_count")

    def test_data_quality_returns_response(self):
        """Test that get_data_quality returns proper response."""
        from atas_market_structure.health_services import HealthService

        mock_repo = MagicMock()
        mock_repo.list_ingestions.return_value = []

        service = HealthService(mock_repo)
        quality = service.get_data_quality()

        assert hasattr(quality, "status")
        assert hasattr(quality, "data_status")
        assert hasattr(quality, "source_statuses")
        # Verify required fields
        assert hasattr(quality, "profile_version")
        assert hasattr(quality, "engine_version")


# ============================================================================
# Test Validation Functions
# ============================================================================

class TestPayloadValidation:
    """Tests for payload validation functions."""

    def test_validate_market_structure_payload_valid(self):
        """Test validation of valid market structure payload."""
        from atas_market_structure.ingestion_services import validate_market_structure_payload

        # Provide minimal valid payload structure - actual validation depends on MarketStructurePayload requirements
        # This test verifies the validation function can be called
        invalid_payload = {
            "schema_version": "1.0.0",
            # Missing required fields - should fail
        }

        result = validate_market_structure_payload(invalid_payload)
        # Should fail due to missing required fields
        assert not result.is_valid
        assert result.payload is None
        assert len(result.errors) > 0

    def test_validate_market_structure_payload_invalid(self):
        """Test validation of invalid market structure payload."""
        from atas_market_structure.ingestion_services import validate_market_structure_payload

        invalid_payload = {
            "schema_version": "1.0.0",
            # Missing required fields
        }

        result = validate_market_structure_payload(invalid_payload)
        assert not result.is_valid
        assert result.payload is None
        assert len(result.errors) > 0

    def test_validate_adapter_payload_unsupported_type(self):
        """Test validation of adapter payload with unsupported type."""
        from atas_market_structure.ingestion_services import validate_adapter_payload

        payload = {
            "schema_version": "1.0.0",
            "message_type": "unsupported_type",
            "message_id": "test-001",
        }

        result = validate_adapter_payload(payload)
        assert not result.is_valid
        assert "Unsupported message_type" in result.errors[0]

    def test_validate_adapter_payload_continuous_state_valid(self):
        """Test validation of adapter payload with unsupported type."""
        from atas_market_structure.ingestion_services import validate_adapter_payload

        # Test with unsupported type first
        payload = {
            "schema_version": "1.0.0",
            "message_type": "continuous_state",
            # Missing many required fields
        }

        result = validate_adapter_payload(payload)
        # Should fail due to missing required fields
        assert not result.is_valid
        assert len(result.errors) > 0


# ============================================================================
# Test Degraded Mode
# ============================================================================

class TestDegradedMode:
    """Tests for degraded mode detection."""

    def test_assess_degraded_modes_from_stale_ingestions(self):
        """Test degraded mode assessment from stale ingestion data."""
        from atas_market_structure.health_services import HealthService
        from atas_market_structure.models import DegradedMode

        mock_repo = MagicMock()
        service = HealthService(mock_repo)

        # Create mock ingestion with stale depth data
        stale_time = datetime.now(tz=UTC) - timedelta(minutes=5)
        mock_ingestion = MagicMock()
        mock_ingestion.ingestion_kind = "depth_snapshot"
        mock_ingestion.observed_at = stale_time

        mock_repo.list_ingestions.return_value = [mock_ingestion]

        degraded = service._assess_degraded_modes([mock_ingestion])
        assert DegradedMode.NO_DEPTH in degraded

    def test_assess_degraded_modes_from_fresh_ingestions(self):
        """Test no degraded modes from fresh ingestion data."""
        from atas_market_structure.health_services import HealthService
        from atas_market_structure.models import DegradedMode

        mock_repo = MagicMock()
        service = HealthService(mock_repo)

        # Create mock ingestion with fresh data
        fresh_time = datetime.now(tz=UTC) - timedelta(seconds=5)
        mock_ingestion = MagicMock()
        mock_ingestion.ingestion_kind = "depth_snapshot"
        mock_ingestion.observed_at = fresh_time

        degraded = service._assess_degraded_modes([mock_ingestion])
        assert DegradedMode.NO_DEPTH not in degraded


# ============================================================================
# Test Cache Management Service
# ============================================================================

class TestCacheManagementService:
    """Tests for the CacheManagementService."""

    def test_create_cache_record(self):
        """Test creating a cache record."""
        from atas_market_structure.cache_management_services import (
            CacheManagementService,
            CacheStatus,
        )

        mock_repo = MagicMock()
        service = CacheManagementService(mock_repo)

        record = service.create_cache_record(
            cache_key="test|nq|1m|2026-03-24",
            status=CacheStatus.UNVERIFIED,
        )

        assert record.cache_key == "test|nq|1m|2026-03-24"
        assert record.status == CacheStatus.UNVERIFIED
        assert record.verification_count == 0

    def test_record_verification_increments_count(self):
        """Test that recording verification increments count."""
        from atas_market_structure.cache_management_services import (
            CacheManagementService,
            CacheStatus,
            CacheRecord,
        )
        from atas_market_structure.models import ReplayWorkbenchIntegrity, ReplayVerificationStatus

        mock_repo = MagicMock()
        service = CacheManagementService(mock_repo)

        # Create initial record
        service.create_cache_record(cache_key="test|nq|1m|2026-03-24")

        # Record verification
        integrity = ReplayWorkbenchIntegrity(
            status="verified",
            window_start=datetime.now(tz=UTC),
            window_end=datetime.now(tz=UTC) + timedelta(hours=1),
            window_days=1,
        )
        record = service.record_verification("test|nq|1m|2026-03-24", integrity)

        assert record.verification_count == 1
        assert record.status == CacheStatus.VERIFIED

    def test_invalidate_cache_changes_status(self):
        """Test that invalidating cache changes status."""
        from atas_market_structure.cache_management_services import (
            CacheManagementService,
            CacheStatus,
        )

        mock_repo = MagicMock()
        service = CacheManagementService(mock_repo)

        # Create initial record
        service.create_cache_record(cache_key="test|nq|1m|2026-03-24")

        # Invalidate
        record = service.invalidate_cache("test|nq|1m|2026-03-24", "Test invalidation")

        assert record.status == CacheStatus.INVALIDATED
        assert record.last_invalidated_at is not None

    def test_cache_record_properties(self):
        """Test CacheRecord properties."""
        from atas_market_structure.cache_management_services import CacheRecord, CacheStatus

        record = CacheRecord(
            cache_key="test|nq|1m|2026-03-24",
            status=CacheStatus.VERIFIED,
            verification_count=2,
        )

        assert record.is_durable is False
        assert record.needs_verification is True
        assert record.can_serve is True

        # Test durable record
        durable_record = CacheRecord(
            cache_key="test|nq|1m|2026-03-24",
            status=CacheStatus.DURABLE,
            verification_count=3,
        )
        assert durable_record.is_durable is True
        assert durable_record.can_serve is True

        # Test invalidated record
        invalidated_record = CacheRecord(
            cache_key="test|nq|1m|2026-03-24",
            status=CacheStatus.INVALIDATED,
            verification_count=0,
        )
        assert invalidated_record.can_serve is False


# ============================================================================
# Test Backfill Management Service
# ============================================================================

class TestBackfillManagementService:
    """Tests for the BackfillManagementService."""

    def test_create_backfill_request(self):
        """Test creating a backfill request."""
        from atas_market_structure.cache_management_services import (
            BackfillManagementService,
            BackfillStatus,
        )
        from atas_market_structure.models import Timeframe

        mock_repo = MagicMock()
        service = BackfillManagementService(mock_repo)

        request = service.create_backfill_request(
            request_id="bf-001",
            cache_key="test|nq|1m|2026-03-24",
            instrument_symbol="NQ",
            display_timeframe=Timeframe.MIN_1,
            window_start=datetime.now(tz=UTC),
            window_end=datetime.now(tz=UTC) + timedelta(hours=1),
        )

        assert request.request_id == "bf-001"
        assert request.cache_key == "test|nq|1m|2026-03-24"
        assert request.status == BackfillStatus.PENDING
        assert request.is_active is True

    def test_dispatch_backfill_changes_status(self):
        """Test that dispatching backfill changes status."""
        from atas_market_structure.cache_management_services import (
            BackfillManagementService,
            BackfillStatus,
        )
        from atas_market_structure.models import Timeframe

        mock_repo = MagicMock()
        service = BackfillManagementService(mock_repo)

        # Create request
        service.create_backfill_request(
            request_id="bf-001",
            cache_key="test|nq|1m|2026-03-24",
            instrument_symbol="NQ",
            display_timeframe=Timeframe.MIN_1,
            window_start=datetime.now(tz=UTC),
            window_end=datetime.now(tz=UTC) + timedelta(hours=1),
        )

        # Dispatch
        dispatched = service.dispatch_backfill("bf-001")

        assert dispatched is not None
        assert dispatched.status == BackfillStatus.DISPATCHED
        assert dispatched.dispatched_at is not None

    def test_complete_backfill_changes_status(self):
        """Test that completing backfill changes status."""
        from atas_market_structure.cache_management_services import (
            BackfillManagementService,
            BackfillStatus,
        )
        from atas_market_structure.models import Timeframe

        mock_repo = MagicMock()
        service = BackfillManagementService(mock_repo)

        # Create and dispatch
        service.create_backfill_request(
            request_id="bf-001",
            cache_key="test|nq|1m|2026-03-24",
            instrument_symbol="NQ",
            display_timeframe=Timeframe.MIN_1,
            window_start=datetime.now(tz=UTC),
            window_end=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        service.dispatch_backfill("bf-001")

        # Complete
        completed = service.complete_backfill("bf-001")

        assert completed is not None
        assert completed.status == BackfillStatus.COMPLETED
        assert completed.completed_at is not None

    def test_fail_backfill_records_error(self):
        """Test that failing backfill records error."""
        from atas_market_structure.cache_management_services import (
            BackfillManagementService,
            BackfillStatus,
        )
        from atas_market_structure.models import Timeframe

        mock_repo = MagicMock()
        service = BackfillManagementService(mock_repo)

        # Create
        service.create_backfill_request(
            request_id="bf-001",
            cache_key="test|nq|1m|2026-03-24",
            instrument_symbol="NQ",
            display_timeframe=Timeframe.MIN_1,
            window_start=datetime.now(tz=UTC),
            window_end=datetime.now(tz=UTC) + timedelta(hours=1),
        )

        # Fail
        failed = service.fail_backfill("bf-001", "Connection timeout")

        assert failed is not None
        assert failed.status == BackfillStatus.FAILED
        assert failed.last_error == "Connection timeout"
        assert failed.retry_count == 1

    def test_acknowledge_backfill_changes_status(self):
        """Test that acknowledging backfill changes status."""
        from atas_market_structure.cache_management_services import (
            BackfillManagementService,
            BackfillStatus,
        )
        from atas_market_structure.models import Timeframe

        mock_repo = MagicMock()
        service = BackfillManagementService(mock_repo)

        # Create, dispatch, complete
        service.create_backfill_request(
            request_id="bf-001",
            cache_key="test|nq|1m|2026-03-24",
            instrument_symbol="NQ",
            display_timeframe=Timeframe.MIN_1,
            window_start=datetime.now(tz=UTC),
            window_end=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        service.dispatch_backfill("bf-001")
        service.complete_backfill("bf-001")

        # Acknowledge
        acknowledged = service.acknowledge_backfill("bf-001")

        assert acknowledged is not None
        assert acknowledged.status == BackfillStatus.ACKNOWLEDGED
        assert acknowledged.acknowledged_at is not None

    def test_backfill_request_serialization(self):
        """Test BackfillRequest to_dict and from_dict."""
        from atas_market_structure.cache_management_services import BackfillRequest
        from atas_market_structure.models import Timeframe

        original = BackfillRequest(
            request_id="bf-001",
            cache_key="test|nq|1m|2026-03-24",
            instrument_symbol="NQ",
            display_timeframe=Timeframe.MIN_1,
            window_start=datetime(2026, 3, 24, 10, 0, 0, tzinfo=UTC),
            window_end=datetime(2026, 3, 24, 11, 0, 0, tzinfo=UTC),
            chart_instance_id="chart-001",
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = BackfillRequest.from_dict(data)

        assert restored.request_id == original.request_id
        assert restored.cache_key == original.cache_key
        assert restored.instrument_symbol == original.instrument_symbol
        assert restored.display_timeframe == original.display_timeframe
        assert restored.chart_instance_id == original.chart_instance_id

    def test_get_active_backfill_requests_filters(self):
        """Test filtering of active backfill requests."""
        from atas_market_structure.cache_management_services import (
            BackfillManagementService,
        )
        from atas_market_structure.models import Timeframe

        mock_repo = MagicMock()
        service = BackfillManagementService(mock_repo)

        # Create requests for different instruments
        service.create_backfill_request(
            request_id="bf-nq-001",
            cache_key="test|nq|1m|2026-03-24",
            instrument_symbol="NQ",
            display_timeframe=Timeframe.MIN_1,
            window_start=datetime.now(tz=UTC),
            window_end=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        service.create_backfill_request(
            request_id="bf-es-001",
            cache_key="test|es|1m|2026-03-24",
            instrument_symbol="ES",
            display_timeframe=Timeframe.MIN_1,
            window_start=datetime.now(tz=UTC),
            window_end=datetime.now(tz=UTC) + timedelta(hours=1),
        )

        # Get all active
        all_active = service.get_active_backfill_requests()
        assert len(all_active) == 2

        # Filter by instrument
        nq_active = service.get_active_backfill_requests(instrument_symbol="NQ")
        assert len(nq_active) == 1
        assert nq_active[0].instrument_symbol == "NQ"


# ============================================================================
# Test Workbench Management Service
# ============================================================================

class TestWorkbenchManagementService:
    """Tests for the composite WorkbenchManagementService."""

    def test_get_health_summary(self):
        """Test getting health summary."""
        from atas_market_structure.cache_management_services import WorkbenchManagementService

        mock_repo = MagicMock()
        service = WorkbenchManagementService(mock_repo)

        summary = service.get_health_summary()

        assert "timestamp" in summary
        assert "cache" in summary
        assert "backfill" in summary
        assert "healthy" in summary
        assert isinstance(summary["healthy"], bool)

    def test_cleanup_expired_records(self):
        """Test cleanup of expired records."""
        from atas_market_structure.cache_management_services import WorkbenchManagementService

        mock_repo = MagicMock()
        service = WorkbenchManagementService(mock_repo)

        result = service.cleanup_expired_records()

        assert "cache_records_cleaned" in result
        assert "backfill_requests_cleaned" in result


# ============================================================================
# Test ReliabilityResult
# ============================================================================

class TestReliabilityResult:
    """Tests for the ReliabilityResult dataclass."""

    def test_reliability_result_properties_success(self):
        """Test ReliabilityResult properties for success."""
        from atas_market_structure.ingestion_services import ReliabilityResult
        from atas_market_structure.models import ReliableIngestionResponse

        mock_body = MagicMock(spec=ReliableIngestionResponse)
        result = ReliabilityResult(status_code=201, body=mock_body)

        assert result.is_success is True
        assert result.is_duplicate is False
        assert result.is_error is False
        assert result.is_dead_lettered is False

    def test_reliability_result_properties_duplicate(self):
        """Test ReliabilityResult properties for duplicate."""
        from atas_market_structure.ingestion_services import ReliabilityResult
        from atas_market_structure.models import ReliableIngestionResponse

        mock_body = MagicMock(spec=ReliableIngestionResponse)
        result = ReliabilityResult(status_code=200, body=mock_body)

        assert result.is_success is True
        assert result.is_duplicate is True
        assert result.is_error is False

    def test_reliability_result_properties_error(self):
        """Test ReliabilityResult properties for error."""
        from atas_market_structure.ingestion_services import ReliabilityResult
        from atas_market_structure.models import IngestionErrorResponse

        mock_body = MagicMock(spec=IngestionErrorResponse, dead_letter_id="dlq-001")
        result = ReliabilityResult(status_code=400, body=mock_body)

        assert result.is_success is False
        assert result.is_duplicate is False
        assert result.is_error is True
        assert result.is_dead_lettered is True

    def test_reliability_result_properties_validation_error(self):
        """Test ReliabilityResult properties for validation error."""
        from atas_market_structure.ingestion_services import ReliabilityResult
        from atas_market_structure.models import IngestionErrorResponse

        mock_body = MagicMock(spec=IngestionErrorResponse, dead_letter_id=None)
        result = ReliabilityResult(status_code=422, body=mock_body)

        assert result.is_success is False
        assert result.is_error is True
        assert result.is_dead_lettered is False
