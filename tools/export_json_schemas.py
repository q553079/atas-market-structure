from __future__ import annotations

from pathlib import Path
import json

from atas_market_structure.models import (
    AdapterContinuousStatePayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintPayload,
    AdapterTriggerBurstPayload,
    BeliefLatestEnvelope,
    BeliefStateSnapshot,
    DepthSnapshotPayload,
    EpisodeEvaluation,
    EpisodeEvaluationEnvelope,
    EpisodeListEnvelope,
    EventSnapshotPayload,
    EventEpisode,
    EventHypothesisStateContract,
    FeatureSliceContract,
    InstrumentProfile,
    MarketStructurePayload,
    RecognizerBuild,
    RegimePosteriorContract,
    ReplayAiChatRequest,
    ReplayAiChatResponse,
    ReplayAiReviewRequest,
    ReplayAiReviewResponse,
    ReplayOperatorEntryRequest,
    ReplayOperatorEntryEnvelope,
    ReplayWorkbenchBeliefTimelineEnvelope,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchEpisodeEvaluationListEnvelope,
    ReplayWorkbenchEpisodeReviewEnvelope,
    ReplayWorkbenchHealthStatusEnvelope,
    ReplayWorkbenchLiveTailResponse,
    ReplayWorkbenchLiveStatusResponse,
    ReplayWorkbenchProfileEngineEnvelope,
    ReplayWorkbenchProjectionEnvelope,
    ReplayWorkbenchRebuildLatestRequest,
    ReplayWorkbenchRebuildLatestResponse,
    ReplayWorkbenchSnapshotPayload,
    ReplayWorkbenchTuningReviewEnvelope,
    TuningInputBundle,
    TuningRecommendation,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def write_schema(filename: str, schema: dict[str, object]) -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    path = SCHEMA_DIR / filename
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> None:
    schema_exports: dict[str, type] = {
        "market_structure.schema.json": MarketStructurePayload,
        "event_snapshot.schema.json": EventSnapshotPayload,
        "depth_snapshot.schema.json": DepthSnapshotPayload,
        "atas_adapter.continuous_state.schema.json": AdapterContinuousStatePayload,
        "atas_adapter.history_bars.schema.json": AdapterHistoryBarsPayload,
        "atas_adapter.history_footprint.schema.json": AdapterHistoryFootprintPayload,
        "atas_adapter.trigger_burst.schema.json": AdapterTriggerBurstPayload,
        "instrument_profile_v1.schema.json": InstrumentProfile,
        "recognizer_build_v1.schema.json": RecognizerBuild,
        "feature_slice_v1.schema.json": FeatureSliceContract,
        "regime_posterior_v1.schema.json": RegimePosteriorContract,
        "event_hypothesis_state_v1.schema.json": EventHypothesisStateContract,
        "belief_state_snapshot_v1.schema.json": BeliefStateSnapshot,
        "event_episode_v1.schema.json": EventEpisode,
        "episode_evaluation_v1.schema.json": EpisodeEvaluation,
        "tuning_input_bundle_v1.schema.json": TuningInputBundle,
        "tuning_recommendation_v1.schema.json": TuningRecommendation,
        "belief_latest_envelope_v1.schema.json": BeliefLatestEnvelope,
        "episode_list_envelope_v1.schema.json": EpisodeListEnvelope,
        "episode_evaluation_envelope_v1.schema.json": EpisodeEvaluationEnvelope,
        "replay_workbench_belief_timeline_envelope_v1.schema.json": ReplayWorkbenchBeliefTimelineEnvelope,
        "replay_workbench_episode_review_envelope_v1.schema.json": ReplayWorkbenchEpisodeReviewEnvelope,
        "replay_workbench_episode_evaluation_list_envelope_v1.schema.json": ReplayWorkbenchEpisodeEvaluationListEnvelope,
        "replay_workbench_tuning_review_envelope_v1.schema.json": ReplayWorkbenchTuningReviewEnvelope,
        "replay_workbench_profile_engine_envelope_v1.schema.json": ReplayWorkbenchProfileEngineEnvelope,
        "replay_workbench_health_status_envelope_v1.schema.json": ReplayWorkbenchHealthStatusEnvelope,
        "replay_workbench_projection_envelope_v1.schema.json": ReplayWorkbenchProjectionEnvelope,
        "replay_workbench.operator_entry_request.schema.json": ReplayOperatorEntryRequest,
        "replay_workbench.operator_entry_envelope.schema.json": ReplayOperatorEntryEnvelope,
        "replay_workbench.ai_review_request.schema.json": ReplayAiReviewRequest,
        "replay_workbench.ai_review_response.schema.json": ReplayAiReviewResponse,
        "replay_workbench.ai_chat_request.schema.json": ReplayAiChatRequest,
        "replay_workbench.ai_chat_response.schema.json": ReplayAiChatResponse,
        "replay_workbench.build_request.schema.json": ReplayWorkbenchBuildRequest,
        "replay_workbench.live_tail.schema.json": ReplayWorkbenchLiveTailResponse,
        "replay_workbench.live_status.schema.json": ReplayWorkbenchLiveStatusResponse,
        "replay_workbench.rebuild_latest_request.schema.json": ReplayWorkbenchRebuildLatestRequest,
        "replay_workbench.rebuild_latest_response.schema.json": ReplayWorkbenchRebuildLatestResponse,
        "replay_workbench.snapshot.schema.json": ReplayWorkbenchSnapshotPayload,
    }
    for filename, model in schema_exports.items():
        write_schema(filename, model.model_json_schema())


if __name__ == "__main__":
    main()
