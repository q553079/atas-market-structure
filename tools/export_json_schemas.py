from __future__ import annotations

from pathlib import Path
import json

from atas_market_structure.models import (
    AdapterContinuousStatePayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintPayload,
    AdapterTriggerBurstPayload,
    DepthSnapshotPayload,
    EventSnapshotPayload,
    MarketStructurePayload,
    ReplayAiChatRequest,
    ReplayAiChatResponse,
    ReplayAiReviewRequest,
    ReplayAiReviewResponse,
    ReplayOperatorEntryRequest,
    ReplayOperatorEntryEnvelope,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchLiveTailResponse,
    ReplayWorkbenchLiveStatusResponse,
    ReplayWorkbenchRebuildLatestRequest,
    ReplayWorkbenchRebuildLatestResponse,
    ReplayWorkbenchSnapshotPayload,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def write_schema(filename: str, schema: dict[str, object]) -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    path = SCHEMA_DIR / filename
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> None:
    write_schema("market_structure.schema.json", MarketStructurePayload.model_json_schema())
    write_schema("event_snapshot.schema.json", EventSnapshotPayload.model_json_schema())
    write_schema("depth_snapshot.schema.json", DepthSnapshotPayload.model_json_schema())
    write_schema("atas_adapter.continuous_state.schema.json", AdapterContinuousStatePayload.model_json_schema())
    write_schema("atas_adapter.history_bars.schema.json", AdapterHistoryBarsPayload.model_json_schema())
    write_schema("atas_adapter.history_footprint.schema.json", AdapterHistoryFootprintPayload.model_json_schema())
    write_schema("atas_adapter.trigger_burst.schema.json", AdapterTriggerBurstPayload.model_json_schema())
    write_schema("replay_workbench.operator_entry_request.schema.json", ReplayOperatorEntryRequest.model_json_schema())
    write_schema("replay_workbench.operator_entry_envelope.schema.json", ReplayOperatorEntryEnvelope.model_json_schema())
    write_schema("replay_workbench.ai_review_request.schema.json", ReplayAiReviewRequest.model_json_schema())
    write_schema("replay_workbench.ai_review_response.schema.json", ReplayAiReviewResponse.model_json_schema())
    write_schema("replay_workbench.ai_chat_request.schema.json", ReplayAiChatRequest.model_json_schema())
    write_schema("replay_workbench.ai_chat_response.schema.json", ReplayAiChatResponse.model_json_schema())
    write_schema("replay_workbench.build_request.schema.json", ReplayWorkbenchBuildRequest.model_json_schema())
    write_schema("replay_workbench.live_tail.schema.json", ReplayWorkbenchLiveTailResponse.model_json_schema())
    write_schema("replay_workbench.live_status.schema.json", ReplayWorkbenchLiveStatusResponse.model_json_schema())
    write_schema("replay_workbench.rebuild_latest_request.schema.json", ReplayWorkbenchRebuildLatestRequest.model_json_schema())
    write_schema("replay_workbench.rebuild_latest_response.schema.json", ReplayWorkbenchRebuildLatestResponse.model_json_schema())
    write_schema("replay_workbench.snapshot.schema.json", ReplayWorkbenchSnapshotPayload.model_json_schema())


if __name__ == "__main__":
    main()
