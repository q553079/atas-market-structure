# V1 Recognizer: Recognition Flow & Phase State Machine

## Overview

The V1 Recognizer is a deterministic, rule-driven market structure event identification engine.
It does **not** use LLM/AI in the critical recognition path.
AI is used only for offline tuning recommendations and episode review.

## Recognition Pipeline

```
observation
    │
    ▼
feature_builder.build()  ──► RecognitionFeatureVector
    │                              │
    │  metrics:                   │  evidence_buckets:
    │  - tick_size               │  - bar_structure
    │  - current_direction       │  - volatility_range
    │  - trend_efficiency        │  - trend_efficiency
    │  - initiative_*_score      │  - initiative
    │  - balance_score          │  - balance
    │  - absorption_score       │  - absorption
    │  - depth_dom_score         │  - depth_dom
    │  - anchor_interaction_*   │  - anchor_interaction
    │  - path_dependency_*      │  - path_dependency
    │
    ▼
regime_updater.build()  ──► list[RegimePosteriorRecord]
    │
    │  Six regime kinds (softmax-normalized):
    │  - STRONG_MOMENTUM_TREND
    │  - WEAK_MOMENTUM_TREND_NARROW
    │  - WEAK_MOMENTUM_TREND_WIDE
    │  - BALANCE_MEAN_REVERSION
    │  - COMPRESSION
    │  - TRANSITION_EXHAUSTION
    │
    ▼
event_updater.build()  ──► list[EventHypothesisState]
    │
    │  Four hypothesis kinds (softmax-normalized):
    │  - CONTINUATION_BASE          → momentum_continuation
    │  - DISTRIBUTION_BALANCE       → balance_mean_reversion
    │  - ABSORPTION_ACCUMULATION   → absorption_to_reversal_prep
    │  - REVERSAL_PREPARATION      → absorption_to_reversal_prep
    │
    │  Phase (from phase_machine.compute_phase):
    │  EMERGING → BUILDING → CONFIRMING → RESOLVED | INVALIDATED
    │                  │            │
    │                  ▼            ▼
    │               WEAKENING   WEAKENING
    │                  │            │
    │                  ▼            ▼
    │             INVALIDATED   INVALIDATED
    │
    ▼
belief_state_builder.build_and_store()  ──► BeliefStateSnapshot
    │  Append-only. Top 3 regimes + top 3 hypotheses.
    │
    ▼
episode_closer.close_episodes()  ──► list[EventEpisode]
    │  Episode resolution:
    │  - CONFIRMED:    RESOLVED phase reached
    │  - INVALIDATED:  INVALIDATED phase reached
    │  - REPLACED:     superseded by another event kind
    │  - TIMED_OUT:    exceeded max duration
    │  - EXPIRED:      exceeded episode duration
    │
    ▼
episode_evaluator.evaluate_episode()  ──► EpisodeEvaluation (offline)
```

## Phase State Machine

### Phase Lifecycle

```
EMERGING ──► BUILDING ──► CONFIRMING ──► RESOLVED (success)
    │           │              │
    │           ▼              ▼
    │        WEAKENING      WEAKENING
    │           │              │
    │           ▼              ▼
    └─────► INVALIDATED ◄──────┘
```

### V1 Event Phase Rules

#### momentum_continuation (CONTINUATION_BASE)

| Phase      | Condition                                                    |
|------------|--------------------------------------------------------------|
| RESOLVED   | prob >= 0.74 + initiative >= 0.68 + distance > 10 ticks    |
| INVALIDATED| distance <= 10 ticks (returned to balance center)          |
| INVALIDATED| opposite_initiative >= 0.45                               |
| INVALIDATED| absorption >= 0.55 (against trend)                        |
| WEAKENING  | prior_prob - prob >= 0.12 AND prob >= 0.56               |
| CONFIRMING | prob >= 0.56 (but not resolved/invalidated)               |
| BUILDING   | prob >= 0.36 AND prob < 0.56                              |
| EMERGING   | prob < 0.36                                                |

#### balance_mean_reversion (DISTRIBUTION_BALANCE)

| Phase      | Condition                                                     |
|------------|---------------------------------------------------------------|
| RESOLVED   | prob >= 0.56 + distance <= 10 ticks                         |
| INVALIDATED| initiative >= 0.68 + distance > 20 ticks (breakout)          |
| WEAKENING  | prior_prob - prob >= 0.12 AND prob >= 0.36                    |
| CONFIRMING | prob >= 0.56 (but not resolved/invalidated)                  |
| BUILDING   | prob >= 0.36 AND prob < 0.56                                |
| EMERGING   | prob < 0.36                                                  |

#### absorption_to_reversal_preparation (ABSORPTION_ACCUMULATION)

| Phase      | Condition                                                     |
|------------|---------------------------------------------------------------|
| INVALIDATED| initiative >= 0.68 + absorption < 0.45                         |
| INVALIDATED| initiative >= 0.68 + trend_efficiency >= 0.60                 |
| WEAKENING  | prior_prob - prob >= 0.12 AND prob >= 0.36                    |
| CONFIRMING | prob >= 0.56                                                 |
| BUILDING   | prob >= 0.36 AND prob < 0.56                                 |
| EMERGING   | prob < 0.36                                                  |

#### absorption_to_reversal_preparation (REVERSAL_PREPARATION)

| Phase      | Condition                                                     |
|------------|---------------------------------------------------------------|
| RESOLVED   | prob >= 0.74 + absorption >= 0.55 + opposite >= 0.30         |
| INVALIDATED| initiative >= 0.68 + balance < 0.65                           |
| INVALIDATED| balance >= 0.70 + opposite < 0.25 (stuck balance)           |
| WEAKENING  | prior_prob - prob >= 0.12 AND prob >= 0.36                    |
| CONFIRMING | prob >= 0.56                                                 |
| BUILDING   | prob >= 0.36 AND prob < 0.56                                 |
| EMERGING   | prob < 0.36                                                  |

## Data Structures

### RecognitionFeatureVector

Deterministic feature slice derived from append-only observations.

```
metrics: dict[str, float]
  - tick_size, current_direction, trend_efficiency
  - range_expansion_score, compression_score, overlap_ratio
  - initiative_buy_score, initiative_sell_score
  - balance_score, absorption_score, depth_dom_score
  - anchor_interaction_score, path_dependency_score
  - balance_center_price, distance_to_balance_center_ticks

evidence_buckets: dict[str, EvidenceBucket]
  - bar_structure, volatility_range, trend_efficiency
  - initiative, balance, absorption, depth_dom
  - anchor_interaction, path_dependency
```

### RegimePosteriorRecord

```
regime: RegimeKind
probability: float (0.0 - 1.0, softmax-normalized)
evidence: list[str]  (top 3 supporting bucket names)
```

### EventHypothesisState

```
hypothesis_id: str  (stable hash-based ID)
hypothesis_kind: EventHypothesisKind
mapped_event_kind: TradableEventKind
phase: EventPhase
posterior_probability: float
supporting_evidence: list[str]
missing_confirmation: list[str]
invalidating_signals: list[str]
transition_watch: list[str]
data_quality_score, evidence_density_score,
model_stability_score, anchor_dependence_score: float
```

### BeliefStateSnapshot

```
belief_state_id: str
regime_posteriors: list[RegimePosteriorRecord]  (top 3)
event_hypotheses: list[EventHypothesisState]     (top 3)
active_anchors: list[MemoryAnchorSnapshot]       (top 3)
missing_confirmation: list[str]
invalidating_signals_seen: list[str]
transition_watch: list[str]
```

### EventEpisode

```
episode_id: str
event_kind: TradableEventKind
hypothesis_kind: EventHypothesisKind
phase: EventPhase  (final phase)
resolution: EpisodeResolution
started_at, ended_at: datetime
peak_probability: float
dominant_regime: RegimeKind
supporting_evidence: list[str]
invalidating_evidence: list[str]
key_evidence_summary: list[str]
```

## V1 Event Templates

### momentum_continuation

**Setup:** strong/weak momentum regime, trend_efficiency >= 0.55, initiative_strength >= 0.60
**Confirmation:** initiative_reacceleration >= 0.68, far from balance center
**Invalidation:** back to balance center, opposite initiative >= 0.45, absorption >= 0.55
**Replacement candidates:** balance_mean_reversion, absorption_to_reversal_preparation
**Typical duration:** 30-120 minutes

### balance_mean_reversion

**Setup:** balance/compression regime, balance_center defined, initiative subdued
**Confirmation:** price reached balance center (distance <= 10 ticks)
**Invalidation:** fresh initiative breakout >= 0.70, acceptance away from center
**Replacement candidates:** momentum_continuation, absorption_to_reversal_preparation
**Typical duration:** 60-180 minutes

### absorption_to_reversal_preparation

**Phase 1 - ABSORPTION_ACCUMULATION:**
**Setup:** transition_exhaustion/compression regime, absorption >= 0.55
**Invalidation:** initiative re-acceleration, trend efficiency recovery
**Replacement candidates:** momentum_continuation

**Phase 2 - REVERSAL_PREPARATION:**
**Setup:** absorption >= 0.50, opposite_initiative emerging >= 0.30
**Confirmation:** absorption >= 0.55 + opposite_initiative >= 0.30 + prob >= 0.74
**Invalidation:** same-side re-acceleration, stuck in static balance
**Replacement candidates:** momentum_continuation, balance_mean_reversion
**Typical duration:** 20-90 minutes

## Degraded Modes

When certain data is unavailable, the recognizer continues with degraded evidence:

| Degraded Mode       | Effect                                                    |
|---------------------|-----------------------------------------------------------|
| NO_DEPTH            | depth_dom bucket unavailable, weight reduced              |
| NO_DOM              | DOM evidence suppressed, hard confirms disabled             |
| STALE_MACRO         | Regime probabilities flattened toward uniform (blend=0.15)|
| REPLAY_REBUILD      | Regime probabilities flattened (blend=0.22)                 |

The recognizer **never crashes** due to missing data. It degrades gracefully and continues emitting belief states.

## Key Design Principles

1. **No AI in critical path**: All recognition decisions are rule/feature-driven
2. **Append-only data**: All outputs are immutable, auditable, replayable
3. **Deterministic**: Same input always produces same output
4. **Fixed ontology**: Only 3 V1 events, no arbitrary extension
5. **Graceful degradation**: Missing data reduces quality but doesn't stop recognition
6. **Observable**: Every belief state carries data_status and evidence density scores
