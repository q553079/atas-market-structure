# Storage / Episode Evaluation / Tuning Recommendation 操作指南

> Thread 2 负责数据持久化层，为识别结果提供可评估、可比较、可重建的数据面。

## 数据流概览

```
Observation (append-only)
    │
    ▼
Recognition Pipeline
    │
    ├── Feature Slice ──────► feature_slice 表
    ├── Regime Posterior ────► regime_posterior 表
    ├── Event Hypothesis ───► event_hypothesis_state 表
    │
    ▼
Belief State Snapshot ───────────────► belief_state_snapshot 表
    │
    ▼
Event Episode ─────────────────────────► event_episode 表
    │
    ▼
Episode Evaluation (规则评估) ─────────► episode_evaluation 表
    │
    ▼
Tuning Bundle ────────────────────────► TuningInputBundle (内存)
    │
    ▼
Tuning Recommendation ────────────────► tuning_recommendation 表
    │
    ▼
Patch Candidate ─────────────────────► profile_patch_candidate 表
    │
    ▼
Patch Validation ────────────────────► patch_validation_result 表
    │
    ▼
Patch Promotion ─────────────────────► patch_promotion_history 表
    │
    ▼
Instrument Profile (versioned) ───────► instrument_profile 表
```

## 1. Episode Evaluation 写入

### 数据结构 (`episode_evaluation_v1`)

```python
EpisodeEvaluation(
    evaluation_id="eval-xxx",
    episode_id="ep-xxx",
    instrument="ES",                    # alias: instrument_symbol
    session="us_regular",
    bar_tf="5m",
    market_time_start=datetime(...),
    market_time_end=datetime(...),
    profile_version="es-v1.0.0",
    engine_version="engine-v1",
    schema_version="episode_evaluation_v1",
    initial_regime_top1=RegimeKind.BALANCE_MEAN_REVERSION,
    initial_regime_prob=0.72,
    evaluated_event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
    initial_phase=EventPhase.BUILDING,
    initial_prob=0.42,
    declared_time_window=EpisodeEvaluationDeclaredTimeWindow(
        mode="next_10_bars", bars_min=5, bars_max=15
    ),
    lifecycle=EpisodeEvaluationLifecycle(...),
    outcome=EpisodeEvaluationOutcome(...),
    scores=EpisodeEvaluationScorecard(...),
    diagnosis=EpisodeEvaluationDiagnosis(...),
    tuning_hints=EpisodeEvaluationTuningHints(...),
    evaluated_at=datetime(...),
)
```

### 写入方式

```python
from atas_market_structure.repository import SQLiteAnalysisRepository

repo = SQLiteAnalysisRepository(Path("data/market_structure.db"))
repo.initialize()

repo.save_episode_evaluation(
    evaluation_id="eval-xxx",
    episode_id="ep-xxx",
    instrument_symbol="ES",
    event_kind="balance_mean_reversion",
    evaluated_at=datetime.now(tz=UTC),
    schema_version="episode_evaluation_v1",
    profile_version="es-v1.0.0",
    engine_version="engine-v1",
    evaluation_payload=evaluation.model_dump(mode="json"),
)
```

### 读取方式

```python
stored = repo.get_episode_evaluation("ep-xxx")
evaluation = EpisodeEvaluation.model_validate(stored.evaluation_payload)
```

### Append-only 约束

- `evaluation_id` 是主键，重复写入会抛出 `sqlite3.IntegrityError`
- 不支持 UPDATE/DELETE

---

## 2. Tuning Recommendation 生成与存储

### 流程

```python
from atas_market_structure.tuning_services import TuningBundleBuilder, TuningService

# Step 1: 构建 Tuning Bundle
bundle_builder = TuningBundleBuilder(repository=repo)
bundle = bundle_builder.build_for_instrument("ES", episode_limit=40)

# Step 2: 生成 Recommendation
tuning_service = TuningService(
    repository=repo,
    ai_adapter=None,  # offline-only: 不需要 AI
)
advisory_run = tuning_service.run_advisory(bundle)
# advisory_run.recommendation  # TuningRecommendation
# advisory_run.patch_candidate  # ProfilePatchCandidate (可选)
# advisory_run.validation_result  # ProfilePatchValidationResult (可选)
```

### Tuning Bundle 内容

```python
TuningInputBundle(
    bundle_id="bundle-xxx",
    instrument_symbol="ES",
    schema_version="tuning_input_bundle_v1",
    built_at=datetime.now(tz=UTC),
    profile_version="es-v1.0.0",
    engine_version="engine-v1",
    analysis_window=TuningAnalysisWindow(...),
    instrument_profile=InstrumentProfile(...),
    recent_closed_episodes=[...],        # EventEpisode 列表
    episode_evaluations=[...],          # EpisodeEvaluation 列表
    positive_negative_summary=...,
    patch_history=[...],                 # TuningPatchHistoryEntry 列表
    degradation_statistics=...,
)
```

### Tuning Recommendation 结构

```python
TuningRecommendation(
    recommendation_id="rec-xxx",
    bundle_id="bundle-xxx",
    instrument="ES",
    profile_version="es-v1.0.0",
    engine_version="engine-v1",
    schema_version="tuning_recommendation_v1",
    generated_at=datetime.now(tz=UTC),
    advisor_kind="offline_stub_v1",    # 或 "openai_v1"
    analysis_window=TuningAnalysisWindow(...),
    top_failure_modes=[TuningFailureModeSummary(...)],
    recommendations=[
        TuningRecommendationItem(
            parameter="thresholds.confirming_hypothesis_probability",
            direction="increase",       # increase / decrease / hold
            current_value=0.56,
            proposed_value=0.62,
            support_count=5,
            reason="late_confirmation_pattern",
            expected_improvement="Earlier confirmation signal",
            risk="May trigger on noise",
            confidence="medium",
        ),
    ],
    expected_improvement="...",
    risk="...",
    confidence="medium",
    allow_ai_auto_apply=False,          # 硬约束: AI 不能自动生效
)
```

---

## 3. Patch Candidate 管理

### 创建 Candidate

```python
from atas_market_structure.profile_services import InstrumentProfileService
from atas_market_structure.models import ProfileSuggestedChange

profile_service = InstrumentProfileService(repository=repo)

# 通过 validate_patch 创建 candidate
candidate, validation = profile_service.validate_patch(
    base_profile=current_profile,
    patch={"thresholds.confirming_hypothesis_probability": 0.62},
    proposed_profile_version="es-v1.1.0",
    persist=True,  # 自动保存到数据库
)
# candidate.candidate_id  # 稳定 ID
# candidate.status  # 当前状态
```

### Patch Candidate 状态机

```
candidate_created
       │
       ▼
boundary_validated ◄─── 边界验证通过
       │
       ▼
awaiting_offline_replay ──► replay_compare_runner (离线)
       │
       ▼
validated / rejected
       │
       ▼
awaiting_human_approval ──► 人工审批
       │
       ▼
promoted ────────────────────────────────► instrument_profile (新版本激活)
```

### 状态查询

```python
rows = repo.list_profile_patch_candidates(
    instrument_symbol="ES",
    status="validated",  # 可选过滤
    limit=20,
)
```

---

## 4. Profile 版本比较

### 跨版本 Diff

```python
from atas_market_structure.profile_services import InstrumentProfileService

profile_service = InstrumentProfileService(repository=repo)

preview = profile_service.compare_profile_versions(
    instrument_symbol="ES",
    base_version="es-v1.0.0",
    proposed_version="es-v1.1.0",
)

# preview.base_profile_version       # "es-v1.0.0"
# preview.proposed_profile_version # "es-v1.1.0"
# preview.changed_fields           # [ProfilePatchFieldDiff(...)]
# preview.risk_notes               # ["参数越界风险"]
# preview.requires_human_review    # True
# preview.allow_ai_auto_apply      # False (硬约束)
```

### Profile 版本血缘

```python
versions = repo.list_instrument_profile_versions("ES")
# 返回所有版本，按创建时间排序
for v in versions:
    print(f"{v.profile_version} (active={v.is_active})")

# 获取指定版本
record = repo.get_instrument_profile_version("ES", "es-v1.0.0")
```

---

## 5. Patch Promotion 记录

### 晋升操作

```python
# Step 1: 激活新版本
repo.save_instrument_profile(
    instrument_symbol="ES",
    profile_version="es-v1.1.0",
    schema_version="instrument_profile_v1",
    ontology_version="v1",
    is_active=True,
    profile_payload=proposed_payload,
    created_at=datetime.now(tz=UTC),
)

# Step 2: 记录晋升历史 (append-only)
repo.save_patch_promotion_history(
    promotion_id=f"promo-{uuid4().hex}",
    candidate_id=candidate.candidate_id,
    instrument_symbol="ES",
    promoted_profile_version="es-v1.1.0",
    previous_profile_version="es-v1.0.0",
    promoted_at=datetime.now(tz=UTC),
    promoted_by="operator_chen",
    promotion_notes="Approved after manual review of late_confirmation failure mode.",
    detail={"evaluation_count": 12, "recommendation_id": "rec-xxx"},
)
```

### 查询晋升历史

```python
# 按 candidate 查询
promotions = repo.list_patch_promotions(candidate_id="cand-xxx")

# 按品种查询
es_promotions = repo.list_patch_promotions(instrument_symbol="ES")

# 按晋升 ID 查询
promotion = repo.get_patch_promotion("promo-xxx")
```

---

## 6. Rebuild 支持

所有 `derived` 和 `trajectory` 表的数据都通过 Replay Rebuild 重建：

```python
from atas_market_structure.rebuild_runner import ReplayRebuildRunner

runner = ReplayRebuildRunner()
report = runner.run_case(
    case_id="golden-case-es-20260320",
    target_path=Path("data/rebuild_target.db"),
)
# report.belief_count       # 信念快照数量
# report.episode_count     # Episode 数量
# report.evaluation_count  # Episode Evaluation 数量
```

**重建保证**:
- 所有 derived 数据（feature_slice, regime_posterior, event_hypothesis_state, belief_state_snapshot, event_episode, episode_evaluation）都可以通过 replay rebuild 重建
- observation 表（append-only）是 rebuild 的输入，必须可回放
- rebuild 后原有 append-only 数据不变，新增数据追加

---

## 7. Append-only 约束

| 表 | 主键 | 约束 |
|---|---|---|
| `episode_evaluation` | `evaluation_id` | INSERT OR FAIL |
| `tuning_recommendation` | `recommendation_id` | INSERT OR FAIL |
| `profile_patch_candidate` | `candidate_id` | INSERT OR FAIL |
| `patch_validation_result` | `validation_result_id` | INSERT OR FAIL |
| `patch_promotion_history` | `promotion_id` | INSERT OR FAIL |
| `belief_state_snapshot` | `belief_state_id` | INSERT OR FAIL |
| `event_episode` | `episode_id` | INSERT OR FAIL |

**Versioned 表（支持 UPSERT）**:
- `instrument_profile` - (instrument, profile_version) 复合主键，支持更新 is_active
- `recognizer_build` - engine_version 主键，支持更新状态

---

## 8. 安全约束

- `allow_ai_auto_apply = False` 硬编码在所有 Patch 和 Recommendation 模型中
- Patch promotion 必须经过人工审批
- AI 只进 offline tuning 路径，不进实时识别热更新
