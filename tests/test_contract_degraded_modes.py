from __future__ import annotations

from atas_market_structure.models import BeliefDataStatus, DegradedMode, RecognitionMode


def test_degraded_mode_contract_values_match_canonical_names() -> None:
    assert {item.value for item in DegradedMode} == {
        "none",
        "degraded_no_depth",
        "degraded_no_dom",
        "degraded_no_ai",
        "degraded_stale_macro",
        "replay_rebuild_mode",
    }


def test_legacy_degraded_aliases_are_still_accepted_but_normalized() -> None:
    status = BeliefDataStatus.model_validate(
        {
            "data_freshness_ms": 1200,
            "feature_completeness": 0.6,
            "depth_available": False,
            "dom_available": False,
            "ai_available": False,
            "degraded_modes": ["no_depth", "no_dom", "no_ai", "replay_rebuild"],
            "freshness": "delayed",
            "completeness": "partial",
        }
    )

    assert [item.value for item in status.degraded_modes] == [
        "degraded_no_depth",
        "degraded_no_dom",
        "degraded_no_ai",
        "replay_rebuild_mode",
    ]
    assert RecognitionMode("bar_anchor_only") is RecognitionMode.DEGRADED_NO_DEPTH
    assert RecognitionMode("degraded_stale_context") is RecognitionMode.DEGRADED_NO_DOM
    assert DegradedMode("stale_macro") is DegradedMode.STALE_MACRO
