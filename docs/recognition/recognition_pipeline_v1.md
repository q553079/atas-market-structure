# Recognition Pipeline V1

本文件描述当前仓库已经落地的 deterministic recognition 主链，以及它与 `docs/k_repair/replay_workbench_master_spec_v2.md` 的对齐方式。

## 目标边界

当前 recognition pipeline 明确遵守：

- AI 不进入 recognition 关键路径
- observed facts 与 derived interpretation 严格分离
- feature / posterior / belief / episode / evaluation 均为 append-only
- instrument profile / recognizer build / memory anchor freshness 为 versioned state
- depth/DOM 缺失时降级运行，而不是报错终止
- V1 闭环只覆盖：
  - `momentum_continuation`
  - `balance_mean_reversion`
  - `absorption_to_reversal_preparation`

## 当前实现模块

已落地模块位于 `src/atas_market_structure/recognition/`：

- `feature_builder.py`
- `regime_updater.py`
- `event_updater.py`
- `anchor_manager.py`
- `belief_emitter.py`
- `episode_closer.py`
- `degraded_mode.py`
- `pipeline.py`
- `defaults.py`
- `types.py`

与之配套的 profile / evaluation / rebuild / projection 模块：

- `src/atas_market_structure/ontology.py`
- `src/atas_market_structure/profile_services.py`
- `src/atas_market_structure/evaluation_services.py`
- `src/atas_market_structure/tuning_services.py`
- `src/atas_market_structure/rebuild_runner.py`
- `src/atas_market_structure/workbench_projection_services.py`

## 触发顺序

recognition 只在原始观测已经持久化之后触发。

当前 store-first 路径：

- `market_structure`
- `event_snapshot`
- `process_context`
- `depth_snapshot`
- `adapter_continuous_state`
- `adapter_trigger_burst`
- `adapter_history_bars`
- `adapter_history_footprint`

这保证了：

- ingestion 成功与 recognition 成功解耦
- rebuild 可从 append-only 原始层重跑
- recognition 失败不会导致 observed facts 丢失

## Deterministic 主链

`DeterministicRecognitionService` 当前执行顺序：

1. 解析或补齐 active `instrument_profile`
2. 解析或补齐 active `recognizer_build`
3. 计算 degraded mode / freshness / completeness
4. 从 observations + ingestions 构建 `RecognitionFeatureVector`
5. 写入 append-only `feature_slice`
6. 计算并写入 append-only `regime_posterior`
7. 更新 versioned `memory_anchor` / `memory_anchor_version`
8. 计算并写入 append-only `event_hypothesis_state`
9. 生成 append-only `belief_state_snapshot`
10. 在 hypothesis 终止、替换或确认时闭合 append-only `event_episode`
11. 对闭合 episode 生成 append-only `episode_evaluation_v1`

## 输出契约

当前显式 schema/version 命名：

- `instrument_profile_v1`
- `recognizer_build_v1`
- `feature_slice_v1`
- `regime_posterior_v1`
- `event_hypothesis_state_v1`
- `belief_state_snapshot_v1`
- `event_episode_v1`
- `episode_evaluation_v1`

关键输出统一带：

- `schema_version`
- `profile_version`
- `engine_version`
- `data_status`
- 尽可能带 `freshness`
- 尽可能带 `completeness`

## Ontology 对齐

当前仓库固定 ontology 已与 Master Spec v2 对齐：

### Regime

- `strong_momentum_trend`
- `weak_momentum_trend_narrow`
- `weak_momentum_trend_wide`
- `balance_mean_reversion`
- `compression`
- `transition_exhaustion`

### Event hypothesis

- `continuation_base`
- `distribution_balance`
- `absorption_accumulation`
- `reversal_preparation`

### Phase

- `emerging`
- `building`
- `confirming`
- `weakening`
- `resolved`
- `invalidated`

### Evaluation failure mode

- `none`
- `early_confirmation`
- `late_confirmation`
- `late_invalidation`
- `missed_transition`
- `false_positive`
- `false_negative`

## Degraded mode 规则

当前 canonical degraded mode：

- `degraded_no_depth`
- `degraded_no_dom`
- `degraded_no_ai`
- `degraded_stale_macro`
- `replay_rebuild_mode`

当前 canonical recognition mode：

- `normal`
- `degraded_no_depth`
- `degraded_no_dom`
- `replay_rebuild_mode`

### 关于 `bar_anchor_only`

Master Spec v2 在 7.3A 仍保留了旧字样 `recognition_mode = bar_anchor_only`，但在 degraded enum 和异常场景章节又使用 `degraded_no_depth`。

当前仓库的收口决策是：

- 输出统一使用 `degraded_no_depth`
- 解析层继续兼容旧值 `bar_anchor_only`
- 样例、测试、projection 与 health 输出统一采用 prefixed degraded names

## 当前 evidence buckets

当前 feature builder 已按多证据桶组织：

- `bar_structure`
- `volatility_range`
- `trend_efficiency`
- `initiative`
- `balance`
- `absorption`
- `depth_dom`
- `anchor_interaction`
- `path_dependency`

## 当前 episode / evaluation 闭环

已落地的闭环对象：

- `belief_state_snapshot`
- `event_episode`
- `episode_evaluation_v1`
- `tuning_recommendation_v1`

当前闭合规则：

- hypothesis `resolved` -> `confirmed`
- hypothesis `invalidated` -> `invalidated`
- lead event 被替换 -> `replaced`

当前 evaluation 采用 rule-first：

- 不依赖 AI 才能生成
- 可由 repository 回放重建
- 输出 `diagnosis` 与 `tuning_hints`

## 已知 backlog

当前 recognition 平面仍有 backlog，但不属于本次收口新增方向：

- spec 级 `POST /api/v1/rebuild/belief` HTTP 端点
- tuning recommendation / patch validate / patch promote 的稳定 HTTP 合同
- 真正的 replay compare runner 与 patch promotion 运营流程

## 验证命令

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_recognition_pipeline.py tests/test_golden_replay_cases.py tests/test_rebuild_runner.py -q
```
