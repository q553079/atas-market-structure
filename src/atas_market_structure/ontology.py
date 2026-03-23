from __future__ import annotations

from atas_market_structure.models._enums import (
    EventHypothesisKind,
    EventPhase,
    EvaluationFailureMode,
    RegimeKind,
    TradableEventKind,
)

REGIME_ONTOLOGY: tuple[str, ...] = tuple(item.value for item in RegimeKind)
EVENT_HYPOTHESIS_ONTOLOGY: tuple[str, ...] = tuple(item.value for item in EventHypothesisKind)
TRADABLE_EVENT_ONTOLOGY: tuple[str, ...] = tuple(item.value for item in TradableEventKind)
EVENT_PHASE_ONTOLOGY: tuple[str, ...] = tuple(item.value for item in EventPhase)
EVALUATION_FAILURE_MODE_ONTOLOGY: tuple[str, ...] = tuple(item.value for item in EvaluationFailureMode)

V1_EVENT_TO_HYPOTHESIS: dict[TradableEventKind, tuple[EventHypothesisKind, ...]] = {
    TradableEventKind.MOMENTUM_CONTINUATION: (EventHypothesisKind.CONTINUATION_BASE,),
    TradableEventKind.BALANCE_MEAN_REVERSION: (EventHypothesisKind.DISTRIBUTION_BALANCE,),
    TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION: (
        EventHypothesisKind.ABSORPTION_ACCUMULATION,
        EventHypothesisKind.REVERSAL_PREPARATION,
    ),
}
