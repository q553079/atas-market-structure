from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from atas_market_structure.golden_cases import load_case_sets
from atas_market_structure.models import (
    AdapterContinuousStatePayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintPayload,
    AdapterTriggerBurstPayload,
    BeliefStateSnapshot,
    DepthSnapshotPayload,
    EpisodeEvaluation,
    EventSnapshotPayload,
    MarketStructurePayload,
    ProcessContextPayload,
    ProfilePatchCandidate,
    ProfilePatchValidationResult,
    ReplayAiChatRequest,
    ReplayAiReviewRequest,
    ReplayOperatorEntryRequest,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchRebuildLatestRequest,
    ReplayWorkbenchSnapshotPayload,
    TuningInputBundle,
    TuningRecommendation,
)
from atas_market_structure.profile_loader import InstrumentProfileLoader


class SampleValidationIssue(BaseModel):
    """One validation failure discovered while scanning sample payloads."""

    model_config = ConfigDict(extra="forbid")

    path: str
    error: str


class SampleValidationReport(BaseModel):
    """Summary report for repository sample validation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "sample_validation_report_v1"
    validated_file_count: int = Field(..., ge=0)
    validated_case_count: int = Field(..., ge=0)
    failure_count: int = Field(..., ge=0)
    failures: list[SampleValidationIssue] = Field(default_factory=list)


class SampleValidationService:
    """Validate static repository samples against the current code contracts."""

    def __init__(self) -> None:
        self._profile_loader = InstrumentProfileLoader()

    def validate(self, samples_root: Path) -> SampleValidationReport:
        """Validate every recognized sample file below the requested root."""

        failures: list[SampleValidationIssue] = []
        validated_file_count = 0
        validated_case_count = 0
        for path in sorted(file for file in samples_root.rglob("*") if file.is_file()):
            relative = path.relative_to(samples_root)
            try:
                case_count = self._validate_file(path=path, relative_path=relative)
            except Exception as exc:  # pragma: no cover - exercised via tests
                failures.append(SampleValidationIssue(path=relative.as_posix(), error=str(exc)))
                continue
            validated_file_count += 1
            validated_case_count += case_count
        return SampleValidationReport(
            validated_file_count=validated_file_count,
            validated_case_count=validated_case_count,
            failure_count=len(failures),
            failures=failures,
        )

    def _validate_file(self, *, path: Path, relative_path: Path) -> int:
        rel = relative_path.as_posix()
        if rel.startswith("profiles/") and path.suffix.lower() in {".yaml", ".yml"}:
            self._profile_loader.load(path)
            return 1
        if rel.startswith("episode_evaluations/") and path.suffix.lower() == ".json":
            EpisodeEvaluation.model_validate_json(path.read_text(encoding="utf-8"))
            return 1
        if rel.startswith("recognition/") and path.suffix.lower() == ".json":
            BeliefStateSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
            return 1
        if rel.startswith("tuning/") and path.suffix.lower() == ".json":
            return self._validate_tuning_sample(path)
        if rel.startswith("golden_cases/") and path.suffix.lower() == ".json":
            case_sets = load_case_sets(path)
            return sum(len(case_set.cases) for case_set in case_sets)
        if path.suffix.lower() != ".json":
            raise ValueError("unrecognized sample file type")
        validator = _top_level_sample_validators().get(relative_path.name)
        if validator is None:
            raise ValueError("no validator registered for sample")
        validator(path.read_text(encoding="utf-8"))
        return 1

    @staticmethod
    def _validate_tuning_sample(path: Path) -> int:
        payload = path.read_text(encoding="utf-8")
        if path.name == "tuning_input_bundle.sample.json":
            TuningInputBundle.model_validate_json(payload)
        elif path.name == "tuning_recommendation.sample.json":
            TuningRecommendation.model_validate_json(payload)
        elif path.name == "profile_patch_candidate.sample.json":
            ProfilePatchCandidate.model_validate_json(payload)
        elif path.name == "patch_validation_result.sample.json":
            ProfilePatchValidationResult.model_validate_json(payload)
        else:
            raise ValueError("no tuning sample validator registered")
        return 1


def _top_level_sample_validators():
    return {
        "market_structure.sample.json": MarketStructurePayload.model_validate_json,
        "market_structure.process.sample.json": MarketStructurePayload.model_validate_json,
        "event_snapshot.sample.json": EventSnapshotPayload.model_validate_json,
        "process_context.sample.json": ProcessContextPayload.model_validate_json,
        "depth_snapshot.sample.json": DepthSnapshotPayload.model_validate_json,
        "atas_adapter.continuous_state.sample.json": AdapterContinuousStatePayload.model_validate_json,
        "atas_adapter.history_bars.sample.json": AdapterHistoryBarsPayload.model_validate_json,
        "atas_adapter.history_footprint.sample.json": AdapterHistoryFootprintPayload.model_validate_json,
        "atas_adapter.trigger_burst.sample.json": AdapterTriggerBurstPayload.model_validate_json,
        "replay_workbench.ai_chat_request.sample.json": ReplayAiChatRequest.model_validate_json,
        "replay_workbench.ai_review_request.sample.json": ReplayAiReviewRequest.model_validate_json,
        "replay_workbench.build_request.sample.json": ReplayWorkbenchBuildRequest.model_validate_json,
        "replay_workbench.operator_entry.sample.json": ReplayOperatorEntryRequest.model_validate_json,
        "replay_workbench.rebuild_latest_request.sample.json": ReplayWorkbenchRebuildLatestRequest.model_validate_json,
        "replay_workbench.snapshot.sample.json": ReplayWorkbenchSnapshotPayload.model_validate_json,
    }
