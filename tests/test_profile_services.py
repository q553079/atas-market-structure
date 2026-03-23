from __future__ import annotations

import json
from pathlib import Path

from atas_market_structure.models import PatchValidationStatus
from atas_market_structure.profile_loader import InstrumentProfileLoader
from atas_market_structure.profile_services import (
    InstrumentProfileService,
    build_instrument_profile_v1,
    default_tick_size_for_symbol,
    get_parameter_metadata_registry,
)
from atas_market_structure.repository import SQLiteAnalysisRepository


ROOT = Path(__file__).resolve().parents[1]


def test_sample_profiles_load_and_keep_ai_auto_apply_disabled() -> None:
    loader = InstrumentProfileLoader()

    profiles = loader.load_many(ROOT / "samples" / "profiles")

    assert {profile.instrument_symbol for profile in profiles} == {"CL", "ES", "GC", "NQ"}
    assert all(profile.ontology_version == "master_spec_v2_v1" for profile in profiles)
    assert all(profile.safety.allow_ai_auto_apply is False for profile in profiles)
    assert all(profile.safety.require_offline_validation is True for profile in profiles)


def test_instrument_profile_schema_file_exposes_required_sections() -> None:
    schema = json.loads((ROOT / "schemas" / "instrument_profile_v1.schema.json").read_text(encoding="utf-8"))

    assert schema["title"] == "instrument_profile_v1"
    assert schema["additionalProperties"] is False
    assert {
        "instrument",
        "profile_version",
        "schema_version",
        "ontology_version",
        "normalization",
        "time_windows",
        "thresholds",
        "weights",
        "decay",
        "priors",
        "safety",
    }.issubset(set(schema["required"]))


def test_metadata_registry_uses_instrument_safe_defaults() -> None:
    profile = build_instrument_profile_v1(
        "NQ",
        tick_size=default_tick_size_for_symbol("NQ"),
        profile_version="nq-default",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
    )
    registry = get_parameter_metadata_registry("NQ")

    assert len(registry) >= 50
    assert registry["weights.depth_dom"].safe_default == profile.weights.depth_dom
    assert registry["thresholds.confirming_hypothesis_probability"].safe_default == profile.thresholds.confirming_hypothesis_probability
    assert registry["time_windows.momentum_continuation.normal.bars_max"].safe_default == profile.time_windows.momentum_continuation.normal.bars_max


def test_patch_preview_lists_changed_fields_and_risk_notes() -> None:
    base = build_instrument_profile_v1(
        "NQ",
        tick_size=0.25,
        profile_version="nq-default",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
    )
    service = InstrumentProfileService()

    candidate, validation = service.validate_patch(
        base_profile=base,
        patch={
            "thresholds": {"confirming_hypothesis_probability": 0.60},
            "weights": {"depth_dom": 0.70},
            "time_windows": {"momentum_continuation": {"normal": {"bars_max": 10}}},
        },
        proposed_profile_version="nq-profile-preview-v2",
    )

    assert validation.validation_status is PatchValidationStatus.ACCEPTED
    assert validation.preview is not None
    assert validation.preview.proposed_profile_version == "nq-profile-preview-v2"
    assert set(validation.changed_fields) == {
        "thresholds.confirming_hypothesis_probability",
        "weights.depth_dom",
        "time_windows.momentum_continuation.normal.bars_max",
    }
    assert candidate.suggested_changes["weights.depth_dom"].to_value == 0.7
    assert validation.preview.risk_notes
    assert any("depth_dom" in note for note in validation.preview.risk_notes)


def test_patch_rejects_immutable_ontology_and_ai_auto_apply_fields() -> None:
    base = build_instrument_profile_v1(
        "ES",
        tick_size=0.25,
        profile_version="es-default",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
    )
    service = InstrumentProfileService()

    _, validation = service.validate_patch(
        base_profile=base,
        patch={
            "ontology_version": "mutated",
            "safety": {"allow_ai_auto_apply": True},
        },
    )

    assert validation.validation_status is PatchValidationStatus.REJECTED
    codes = {issue.code for issue in validation.errors}
    assert "immutable_parameter" in codes or "ontology_locked" in codes
    assert "ai_auto_apply_forbidden" in codes or "immutable_parameter" in codes


def test_rejected_patch_is_auditable_in_patch_candidate_storage(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    base = build_instrument_profile_v1(
        "NQ",
        tick_size=0.25,
        profile_version="nq-default",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
    )
    service = InstrumentProfileService(repository=repository)

    candidate, validation = service.validate_patch(
        base_profile=base,
        patch={"weights": {"depth_dom": 2.5}},
        persist=True,
    )

    assert validation.validation_status is PatchValidationStatus.REJECTED
    candidate_rows = repository.list_profile_patch_candidates(instrument_symbol="NQ", limit=10)
    validation_rows = repository.list_patch_validation_results(candidate_id=candidate.candidate_id, limit=10)

    assert candidate_rows
    assert candidate_rows[0].candidate_id == candidate.candidate_id
    assert validation_rows
    assert validation_rows[0].candidate_id == candidate.candidate_id
    assert validation_rows[0].validation_status == PatchValidationStatus.REJECTED.value
