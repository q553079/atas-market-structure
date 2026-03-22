# ATAS Replay Workbench / Event Model / AI Tuning Master Spec v2

状态：Master Spec v2  
用途：本文件是 **唯一主规格书**，用于指导 Codex / 工程师连续实施。  
语言：中文  
适用阶段：Phase 1.5 → Phase 3  
目标：在现有仓库基础上，把“理念文档”升级为“可连续施工的建设蓝图”。

---

# 0. 文档定位

这不是一份“想法备忘录”，也不是一份“泛泛的架构建议”。

这是一份 **面向实施的完整蓝图**，用于把当前项目从：

- ATAS 本地采集与事件快照基础设施
- Replay Workbench 事件理念文档
- 隐状态 / 事件假设 / 记忆锚点模型

推进到：

- 可持续运行的事件识别系统
- 可回放、可审计、可复盘的 belief-state 引擎
- 可降级、可观测、可修复的高可用本地分析服务
- AI 作为“调参与诊断协作者”的安全落地体系

本文件不替代现有仓库文档，而是把现有文档中的核心理念，全部映射为：

- 工程对象
- 数据结构
- 实施顺序
- API 契约
- 测试口径
- 运维与高可用机制
- AI 协作方式

---

# 1. 项目总定义

## 1.1 系统一句话定义

本项目不是静态事件标签识别器，不是单纯指标集合，也不是自动交易系统。

本项目是一个：

**市场隐状态推断 + 事件假设跟踪 + 记忆锚点修正 + Replay Workbench 投影 + AI 诊断协作** 的本地分析系统。

## 1.2 核心交易哲学

系统交易与分析的对象不是“价格本身”，而是：

- 某个市场事件是否正在形成
- 它是否继续按应有方式展开
- 它是否被否决
- 是否有新事件接管旧叙事

因此，系统输出的核心不是“看涨 / 看跌”，而是：

- 当前更像什么 regime
- 当前有哪些并行事件假设
- 哪个事件正在从 emerging 走向 confirming
- 哪些证据支持它
- 还缺什么确认
- 哪些信号说明它正在被否决
- 哪些历史锚点正在影响当前概率

## 1.3 项目边界

### 当前要做

1. 稳定接收和保存 ATAS 侧的结构化观测
2. 构建 deterministic 的 belief-state 引擎
3. 按事件轨迹而不是静态标签做 replay
4. 让系统支持 episode 评估
5. 让 AI 读取 episode 评估与 profile，输出调参建议与候选补丁

### 当前不做

1. 不做在线自动交易
2. 不做 AI 直接控制下单
3. 不做 AI 在线热更新参数
4. 不把 AI 作为底层状态机的替代品
5. 不让 DOM/Heatmap 成为唯一真相来源

---

# 2. 设计总原则

## 2.1 观测与解释分离

所有数据必须分为两类：

- **Observed facts**：原始观测事实，不下结论
- **Derived interpretation**：衍生解释，可重算、可回放、可版本化

这条原则不可破坏。

任何人想“为了方便直接把结论写回原始事件表”，都应视为违规。

## 2.2 事件不是标签，而是轨迹

系统不能把事件当作：

- 一个名字
- 一个标签
- 一个模式匹配结果

而必须把事件表达为轨迹：

- 从哪里开始形成
- 当前在哪个阶段
- 概率为何变化
- 何时应确认
- 何时应降级
- 何时被替换

## 2.3 市场不是无记忆的

历史结构必须以显式对象保存，而不是隐式遗忘。

至少要把以下内容建模为 `memory_anchor`：

- balance center
- accumulation/distribution center
- gap edge
- initiative origin
- high-volume acceptance zone
- trapped inventory zone
- failed breakout reference

## 2.4 多假设并行，拒绝过早单结论

系统不允许强迫自己只保留一个事件标签。

在任何时间点，至少允许：

- 一个主事件假设
- 一到两个竞争事件假设
- 一个 transition watch 列表

## 2.5 AI 负责解释、诊断、建议；规则负责核心产出

底层识别必须是 deterministic、可回放、可测试的。

AI 的职责是：

- 解读 episode
- 总结错误模式
- 给出参数建议
- 生成 patch candidate
- 帮助复盘叙事与工程协作

而不是替代核心状态机。

## 2.6 高可用优先于花哨

“高可用”在本项目中的定义是：

- ATAS 数据偶尔断片时，系统仍能继续运行
- AI 不可用时，belief state 仍照常产出
- depth/DOM 缺失时，系统降级而不是瘫痪
- 旧数据可重放、旧结论可重算、旧版本可追溯

---

# 3. 成功标准

## 3.1 产品成功标准

系统应能在 Replay Workbench 中稳定显示：

1. 当前 regime 概率分布
2. 当前 top event hypotheses
3. 当前 active anchors
4. 当前 data completeness / freshness / staleness 状态
5. 已闭合的 event episodes
6. 每个 episode 的标准化评价
7. AI 给出的调参建议与 patch candidate

## 3.2 识别成功标准

第一阶段，只要求在以下三类事件上形成稳定闭环：

1. `momentum_continuation`
2. `balance_mean_reversion`
3. `absorption_to_reversal_preparation`

稳定闭环的定义：

- 能识别形成过程
- 能表达 validation / invalidation / time window
- 能形成 event_episode
- 能被标准化评估
- 能被 AI 读取并给出调参意见

## 3.3 高可用成功标准

至少满足：

1. AI 不可用时，核心状态识别不受阻
2. depth 输入缺失时，系统降级运行
3. 重启后可从 append-only 观测重建衍生层
4. 所有衍生输出均可追溯到 profile version 与 engine version
5. 所有 patch 必须可回滚

## 3.4 工程成功标准

Codex 完成后，仓库中必须存在：

- 清晰的 schema
- 稳定的 test suite
- 可运行的 replay rebuild
- Golden replay cases
- episode_evaluation_v1
- instrument_profile_v1
- AI tuning I/O contract

---

# 4. 理念 → 工程对象映射表

| 理念对象 | 工程对象 | 是否 append-only | 主要职责 | 说明 |
|---|---|---:|---|---|
| 原始观测 | `observation_*` | 是 | 保存事实 | bars, trades, depth events, gaps, swings |
| 特征切片 | `feature_slice` | 是 | 窗口化数值摘要 | 用于状态更新，不是结论 |
| Hidden Regime | `regime_posterior` | 是 | 表达大背景运行机制 | 6 个主 regime |
| Event Hypothesis | `event_hypothesis_state` | 是 | 表达并行事件后验 | 多假设并行 |
| Memory Anchor | `memory_anchor` | 否（版本化） | 保存历史结构记忆 | 有状态，有 freshness |
| Anchor Interaction | `anchor_interaction` | 是 | 表达当前与历史锚点的互动 | approach/retest/test/revisit |
| Event Episode | `event_episode` | 是 | 保存已形成的轨迹 | start/end/resolution |
| Belief State | `belief_state_snapshot` | 是 | 当前市场理解快照 | UI 与 AI 主要消费对象 |
| Projection | `projection_snapshot` | 是 | `plan/zone/risk/price` 投影 | 投影层，不是底层认知 |
| Episode Evaluation | `episode_evaluation` | 是 | 标准化评估 episode | 为调参与复盘服务 |
| Tuning Recommendation | `tuning_recommendation` | 是 | AI 生成的建议 | 不直接生效 |
| Patch Candidate | `profile_patch_candidate` | 是 | 参数补丁草案 | 需通过验证流程 |
| Profile Version | `instrument_profile` | 否（版本化） | 各品种参数 | ontology 固定，参数可调 |
| Engine Version | `recognizer_build` | 否（版本化） | 识别器版本 | 所有输出都要打上 build id |

---

# 5. 统一事件本体与 V1 范围

## 5.1 Regime 本体（固定 ontology）

V1 固定以下 6 类 regime：

1. `strong_momentum_trend`
2. `weak_momentum_trend_narrow`
3. `weak_momentum_trend_wide`
4. `balance_mean_reversion`
5. `compression`
6. `transition_exhaustion`

注意：regime 是背景，不是事件。

## 5.2 Event Hypothesis 本体（固定 ontology）

V1 核心事件假设层建议保留：

1. `continuation_base`
2. `absorption_accumulation`
3. `profit_taking_pause`
4. `reversal_preparation`
5. `breakout_acceptance`
6. `breakout_rejection`
7. `failed_reversal`
8. `distribution_balance`

## 5.3 Tradable Event V1（第一阶段真正闭环）

Replay Workbench 中用于交易与复盘的可交易事件，V1 只要求闭环这 3 类：

1. `momentum_continuation`
2. `balance_mean_reversion`
3. `absorption_to_reversal_preparation`

其中：

- `momentum_continuation` 主要映射 `continuation_base`
- `balance_mean_reversion` 主要映射 `distribution_balance` / `balance_mean_reversion` 背景下的回归逻辑
- `absorption_to_reversal_preparation` 主要映射 `absorption_accumulation` → `reversal_preparation`

## 5.4 Event Phase（统一生命周期）

所有 event hypothesis 与 event episode 均使用统一 phase：

- `emerging`
- `building`
- `confirming`
- `weakening`
- `resolved`
- `invalidated`

## 5.5 每个可交易事件必须包含的字段

每个 tradable event 模板必须至少包含：

- `initial_hypothesis`
- `validation_rules`
- `invalidation_rules`
- `time_window`
- `replacement_events`

如果缺少上述字段，视为“不可交易事件模板”。

---

# 6. 高可用总架构

## 6.1 总体原则

高可用不能靠“AI 很聪明”实现，只能靠：

- 数据分层
- 降级机制
- 幂等写入
- 版本追踪
- 可重放
- 可重建
- 可观测

## 6.2 运行平面

系统分 5 个平面：

1. **Collector Plane**
   - ATAS / Adapter / Collector DLL
   - 只负责采集与发送

2. **Ingestion Plane**
   - 接收 payload
   - 校验 schema
   - 写入 append-only log
   - 发出 processing job

3. **Recognition Plane**
   - 从观测构建 feature slice
   - 更新 regime posterior / event hypothesis / memory anchor interaction
   - 生成 belief state
   - 形成 event episode

4. **Review & Tuning Plane**
   - episode evaluation
   - AI tuning recommendation
   - patch candidate compare / validate

5. **Projection & UI Plane**
   - Replay Workbench
   - timeline / event overlays / episode review / tuning review

## 6.3 关键高可用设计

### A. 原始观测必须 append-only

无论 recognition 层是否出错，原始观测都必须安全落盘。

### B. 衍生输出必须可重算

所有以下对象都不允许是“唯一真相”：

- feature_slice
- regime posterior
- event hypothesis
- belief state
- projection
- episode evaluation

这些都必须允许从原始观测重建。

### C. AI 不是关键路径

识别链路：

`observation -> feature_slice -> regime/event update -> belief_state`

必须在没有 AI 的情况下完整可运行。

### D. 服务分级健康状态

服务状态分为：

- `healthy`
- `degraded`
- `rebuild_required`
- `paused`

### E. 明确降级模式

至少支持以下降级模式：

1. `degraded_no_depth`
2. `degraded_no_dom`
3. `degraded_no_ai`
4. `degraded_stale_macro`
5. `replay_rebuild_mode`

在降级状态下，不允许假装“系统完全正常”。UI 必须显示降级 badge。

### F. 所有关键输出必须带 freshness 与 completeness

例如 belief state 中应包含：

- `data_freshness_ms`
- `feature_completeness`
- `depth_available`
- `dom_available`
- `ai_available`
- `recognition_mode`

---

# 7. 事件识别高可用蓝图

“事件识别高可用”不是指永远识别对，而是指：

- 数据不完整时仍能给出合理输出
- 不把噪音误当确定性
- 缺证据时会降低置信而不是硬下结论
- 断点后能恢复与重建

## 7.1 识别核心原则

### 1. 先背景，后事件

必须先更新 regime，再更新 event hypotheses。

### 2. 先证据，后命名

先计算 feature/evidence，再进入 hypothesis update。

### 3. 多证据桶，而非单一指标霸权

V1 证据分桶：

- bar structure evidence
- volatility/range evidence
- trend efficiency evidence
- initiative evidence
- balance evidence
- absorption evidence
- depth/DOM evidence
- anchor interaction evidence
- path dependency evidence

### 4. 单个证据缺失时要降级，不可崩溃

例如：depth 缺失时，DOM bucket 降权并标记 unavailable，而不是让整个事件引擎停止。

### 5. 输出必须表达“不确定”

系统必须允许：

- competing hypotheses
- missing confirmation
- invalidation watch
- transition watch

### 6. 事件确认必须加迟滞与节流

为避免闪烁与过拟合，建议：

- `confirming` 进入需满足最小持续条件
- `resolved` / `invalidated` 需要明确触发条件
- 高频抖动时使用 hysteresis

## 7.2 置信度分解

对每个 event hypothesis 的 `probability` 外，再增加：

- `data_quality_score`
- `evidence_density_score`
- `model_stability_score`
- `anchor_dependence_score`

这样 UI 与 AI 能看出：

- 是事件本身弱
- 还是数据不全
- 还是当前证据不够密

## 7.3 缺失数据处理策略

### 情况 A：无 depth / DOM

允许继续运行，但：

- `dom_orderflow_checks` 全部标记 unavailable
- 与其有关的 validation rule 不可直接触发 hard confirm
- 输出 `recognition_mode = bar_anchor_only`

### 情况 B：微结构事件稀疏

继续使用：

- bar features
- swing context
- gap context
- memory anchor interaction

### 情况 C：宏观背景未更新

允许继续运行，但增加 `staleness_penalty`，降低 regime 置信。

## 7.4 识别结果最少输出字段

每次 belief state 更新后，必须至少产出：

- top 3 regime probabilities
- top 3 event hypotheses
- active anchors
- missing confirmation
- invalidating signals seen
- transition watch
- data completeness/freshness
- profile_version
- engine_version

---

# 8. 数据与存储蓝图

## 8.1 存储层总原则

V1 可继续使用 SQLite，但必须：

- 开启 WAL
- 读写路径分层
- append-only 表只插不改
- profile / anchor 等状态对象使用 versioning
- rebuild 工具可从 observation 重建衍生层

如果后续进入更高吞吐阶段，再迁移 Postgres。

## 8.2 推荐表结构

### 1. 原始观测层

- `observation_bar`
- `observation_trade_cluster`
- `observation_depth_event`
- `observation_gap_event`
- `observation_swing_event`
- `observation_absorption_event`
- `observation_adapter_payload`

### 2. 特征层

- `feature_slice`

### 3. 状态层

- `regime_posterior`
- `event_hypothesis_state`
- `belief_state_snapshot`
- `projection_snapshot`

### 4. 记忆层

- `memory_anchor`
- `memory_anchor_version`
- `anchor_interaction`

### 5. 轨迹层

- `event_episode`
- `event_episode_evidence`

### 6. 评估与调参层

- `episode_evaluation`
- `tuning_recommendation`
- `profile_patch_candidate`
- `patch_validation_result`

### 7. 版本与运维层

- `instrument_profile`
- `recognizer_build`
- `ingestion_run_log`
- `rebuild_run_log`
- `dead_letter_payload`
- `schema_registry`

## 8.3 主键与索引建议

### 通用规则

所有主表都至少要有：

- `id`
- `instrument`
- `market_time`
- `ingested_at`
- `schema_version`
- `profile_version`（如适用）
- `engine_version`（如适用）

### 关键索引

- `(instrument, market_time)`
- `(instrument, session_date, market_time)`
- `(episode_id)`
- `(anchor_id)`
- `(profile_version)`
- `(engine_version)`

## 8.4 状态对象版本化规则

### append-only 对象

永不更新，只追加：

- observations
- feature slices
- posteriors
- belief states
- episodes
- episode evaluations
- tuning recommendations

### versioned state 对象

允许更新，但必须保留版本历史：

- instrument profile
- memory anchor role profile / freshness
- recognizer build metadata

---

# 9. 核心 Schema 设计

## 9.1 `belief_state_snapshot`

```json
{
  "belief_state_id": "bs_NQ_20260323_094100_0001",
  "instrument": "NQ",
  "market_time": "2026-03-23T09:41:00-07:00",
  "profile_version": "nq_profile_v0.3.2",
  "engine_version": "recognizer_v0.4.0",
  "recognition_mode": "normal",
  "data_status": {
    "data_freshness_ms": 1200,
    "feature_completeness": 0.93,
    "depth_available": true,
    "dom_available": true,
    "ai_available": false
  },
  "regime_probs": {
    "strong_momentum_trend": 0.18,
    "weak_momentum_trend_narrow": 0.31,
    "weak_momentum_trend_wide": 0.14,
    "balance_mean_reversion": 0.12,
    "compression": 0.08,
    "transition_exhaustion": 0.17
  },
  "event_hypotheses": [
    {
      "kind": "continuation_base",
      "phase": "building",
      "probability": 0.46,
      "supporting_evidence": ["shallow_pullback", "trend_efficiency_ok"],
      "missing_confirmation": ["fresh_initiative_push"],
      "invalidating_signals": ["return_to_old_balance_center"]
    },
    {
      "kind": "reversal_preparation",
      "phase": "emerging",
      "probability": 0.22,
      "supporting_evidence": ["absorption_seen"],
      "missing_confirmation": ["acceptance_above_micro_balance"],
      "invalidating_signals": ["new_low_extension"]
    }
  ],
  "active_anchors": [
    {
      "anchor_id": "anc_001",
      "anchor_type": "balance_center",
      "distance_ticks": 6,
      "influence": 0.27
    }
  ],
  "transition_watch": [
    "fresh_bull_initiative",
    "fail_to_make_new_low"
  ]
}
```

## 9.2 `event_episode`

```json
{
  "episode_id": "ep_NQ_20260323_094100_001",
  "instrument": "NQ",
  "kind": "momentum_continuation",
  "phase": "resolved",
  "start_time": "2026-03-23T09:41:00-07:00",
  "end_time": "2026-03-23T09:48:00-07:00",
  "peak_prob": 0.74,
  "dominant_regime": "weak_momentum_trend_narrow",
  "resolution": "confirmed",
  "key_evidence_summary": [
    "prior_push_exists",
    "shallow_pullback",
    "fresh_initiative_relaunch"
  ],
  "replacement_event": null,
  "profile_version": "nq_profile_v0.3.2",
  "engine_version": "recognizer_v0.4.0"
}
```

## 9.3 `episode_evaluation_v1`

```json
{
  "episode_id": "ep_NQ_20260323_094100_001",
  "instrument": "NQ",
  "session": "RTH",
  "bar_tf": "1m",
  "market_time_start": "2026-03-23T09:41:00-07:00",
  "market_time_end": "2026-03-23T09:48:00-07:00",
  "profile_version": "nq_profile_v0.3.2",
  "engine_version": "recognizer_v0.4.0",
  "schema_version": "episode_evaluation_v1",
  "initial_regime_top1": "weak_momentum_trend_narrow",
  "initial_regime_prob": 0.44,
  "evaluated_event_kind": "momentum_continuation",
  "initial_phase": "emerging",
  "initial_prob": 0.38,
  "declared_time_window": {
    "mode": "next_5_bars",
    "bars_max": 5
  },
  "anchor_context": [
    "old_balance_center_nearby",
    "initiative_origin_below"
  ],
  "lifecycle": {
    "started_at": "2026-03-23T09:41:00-07:00",
    "first_validation_hit_at": "2026-03-23T09:43:00-07:00",
    "peak_prob": 0.74,
    "peak_prob_at": "2026-03-23T09:45:00-07:00",
    "first_invalidation_hit_at": null,
    "downgraded_at": null,
    "resolved_at": "2026-03-23T09:48:00-07:00",
    "resolution": "confirmed",
    "replacement_event": null
  },
  "outcome": {
    "did_event_materialize": true,
    "did_partial_materialize": false,
    "dominant_final_event": "momentum_continuation",
    "judgement_source": "rule_review_v1"
  },
  "scores": {
    "hypothesis_selection_score": 2,
    "confirmation_timing_score": 1,
    "invalidation_timing_score": 0,
    "transition_handling_score": 0,
    "calibration_score": 1
  },
  "diagnosis": {
    "primary_failure_mode": "none",
    "supporting_reasons": [
      "fresh_initiative_within_window",
      "did_not_return_to_old_balance_center"
    ],
    "missing_confirmation": [],
    "invalidating_signals_seen": []
  },
  "tuning_hints": {
    "candidate_parameters": [],
    "suggested_direction": {},
    "confidence": "low"
  }
}
```

## 9.4 `instrument_profile_v1`

```yaml
instrument: NQ
profile_version: nq_profile_v0.3.2
ontology_version: ontology_v1

normalization:
  price_unit: ticks
  atr_window_bars: 20
  displacement_normalizer: atr_fraction
  volume_normalizer: rolling_quantile

time_windows:
  momentum_continuation:
    strong:
      bars_min: 2
      bars_max: 6
    normal:
      bars_min: 3
      bars_max: 8
  balance_mean_reversion:
    normal:
      bars_min: 4
      bars_max: 12
  absorption_to_reversal_preparation:
    normal:
      bars_min: 3
      bars_max: 10

thresholds:
  initiative_push:
    displacement_zscore: 1.4
    efficiency_min: 0.58
  shallow_pullback:
    retrace_ratio_max: 0.38
  deep_pullback:
    retrace_ratio_min: 0.55
  balance_return_penalty_trigger:
    distance_to_balance_ticks: 8

weights:
  bar_structure: 1.0
  initiative: 1.1
  balance: 1.0
  absorption: 1.1
  depth_dom: 0.8
  anchor_interaction: 1.0
  path_dependency: 1.0

decay:
  balance_center_half_life_bars: 120
  gap_edge_half_life_bars: 80
  initiative_origin_half_life_bars: 60

priors:
  regime_transition_bias:
    compression_to_breakout_acceptance: 0.58
    compression_to_breakout_rejection: 0.42

safety:
  allow_ai_auto_apply: false
  require_offline_validation: true
```

---

# 10. Episode Evaluation 设计细则

## 10.1 目的

Episode evaluation 不是“交易盈亏表”，而是：

- 标准化识别质量评价
- 标准化调参入口
- AI 诊断的可信输入

## 10.2 五个核心评分维度

每个维度使用 `-2 / -1 / 0 / +1 / +2`：

1. `hypothesis_selection_score`
2. `confirmation_timing_score`
3. `invalidation_timing_score`
4. `transition_handling_score`
5. `calibration_score`

## 10.3 V1 失败模式枚举

V1 只固定以下失败模式：

- `none`
- `early_confirmation`
- `late_confirmation`
- `late_invalidation`
- `missed_transition`
- `false_positive`
- `false_negative`

## 10.4 为什么只先做少量失败模式

因为此阶段最关键的不是把所有错误命名，而是尽快建立：

- episode → evaluation → tuning hint

这条闭环。

## 10.5 评估来源

V1 允许 3 种来源：

- `rule_review_v1`
- `human_review_v1`
- `hybrid_review_v1`

不允许纯 AI 单独给最终评估结论。

---

# 11. AI 调参与协作体系

## 11.1 AI 的正确角色

AI 在本项目中的定位是：

**调参顾问 + 诊断解释层 + 复盘协作层**

不是：

- 底层识别引擎
- 线上自治参数控制器
- 自动下单策略主脑

## 11.2 为什么不能直接让 AI 在线自动调参

因为会引入：

- 最近样本过拟合
- 不可审计
- 不可回滚
- 不可解释
- 参数漂移污染

## 11.3 AI 输入包（Tuning Input Bundle）

AI 接收的结构化输入至少包含：

1. `instrument_profile`
2. 最近 N 个 closed episodes
3. 对应的 `episode_evaluation`
4. 正反样本统计摘要
5. 最近 patch history
6. 当前 recognizer build metadata
7. 降级运行统计（如有）

## 11.4 AI 输出包（Tuning Recommendation）

AI 输出必须结构化，格式至少为：

```json
{
  "instrument": "NQ",
  "profile_version": "nq_profile_v0.3.2",
  "analysis_window": {
    "episode_count": 40,
    "from": "2026-03-10",
    "to": "2026-03-23"
  },
  "top_failure_modes": [
    {
      "kind": "early_confirmation",
      "count": 12,
      "summary": "momentum_continuation frequently confirms before fresh initiative relaunch"
    }
  ],
  "recommendations": [
    {
      "event_kind": "momentum_continuation",
      "parameter": "time_windows.momentum_continuation.normal.bars_max",
      "direction": "decrease",
      "current_value": 8,
      "proposed_value": 6,
      "reason": "late drift without second initiative causes false positive continuation confirmation",
      "expected_improvement": "reduce early_confirmation false positives",
      "risk": "may miss slower valid continuation cases",
      "confidence": "medium"
    }
  ],
  "patch_candidate_ref": "patch_nq_20260323_001"
}
```

## 11.5 AI 安全门

所有 AI recommendation 必须通过：

1. schema validation
2. parameter boundary validation
3. offline replay validation
4. human review / explicit approval

才能晋升为 profile patch。

## 11.6 禁止事项

AI 不得：

- 修改 ontology
- 自动启用 patch
- 改写原始观测
- 直接覆盖 episode evaluation
- 单独决定某次评估真值

---

# 12. Instrument Profile 设计原则

## 12.1 统一 ontology，分离 instrument profile

所有品种共享：

- regime ontology
- event ontology
- phase ontology
- evaluation ontology

不同品种只调整：

- tempo / time_window
- threshold
- evidence weights
- anchor decay
- priors

## 12.2 参数分类

### A. 归一化参数

例如：

- ATR 窗口
- zscore 归一化
- ticks / points 映射

### B. 节奏参数

例如：

- bars_min / bars_max
- expected relaunch window

### C. validation / invalidation 参数

例如：

- shallow pullback 阈值
- balance return penalty trigger
- acceptance hold bars

### D. 证据权重

例如：

- DOM 权重
- anchor interaction 权重
- path dependency 权重

### E. 衰减参数

例如：

- balance center half-life
- gap edge half-life

### F. 先验参数

例如：

- regime transition bias
- event takeover prior

## 12.3 参数边界规则

每个 profile 参数都必须定义：

- `min`
- `max`
- `step`
- `safe_default`
- `criticality`

这样 AI 才不会给出无意义或危险 patch。

---

# 13. API 蓝图

## 13.1 Ingestion APIs

### `POST /api/v1/ingest/market-structure`

作用：接收市场结构快照

### `POST /api/v1/ingest/event-snapshot`

作用：接收关键事件快照

### `POST /api/v1/ingest/process-context`

作用：接收 process-aware 上下文

### `POST /api/v1/ingest/depth-snapshot`

作用：接收 depth snapshot

### `POST /api/v1/ingest/adapter-payload`

作用：接收 adapter 原始消息

## 13.2 Recognition APIs

### `GET /api/v1/belief/latest?instrument=NQ`

返回最新 belief state

### `GET /api/v1/episodes/latest?instrument=NQ`

返回最近闭合 episodes

### `POST /api/v1/rebuild/belief`

从原始观测重建 feature / belief / episode

## 13.3 Review APIs

### `POST /api/v1/review/episode-evaluation`

写入 episode evaluation

### `GET /api/v1/review/episode-evaluation/{episode_id}`

读取 episode evaluation

## 13.4 Tuning APIs

### `POST /api/v1/tuning/recommendation`

输入：structured tuning bundle  
输出：AI tuning recommendation

### `POST /api/v1/tuning/patch/validate`

输入：patch candidate  
输出：offline validation result

### `POST /api/v1/tuning/patch/promote`

仅在 validation pass 且人工确认后可用

## 13.5 Health APIs

### `GET /health`

返回服务总健康

### `GET /health/ingestion`

返回 ingestion 健康

### `GET /health/recognition`

返回 recognition 健康与 lag

### `GET /health/data-quality`

返回 data freshness / completeness / degraded mode

---

# 14. Replay Workbench UI 蓝图

## 14.1 UI 不是“看 K 线加几个提示词”

UI 应该成为 belief-state 与 episode 的观测器。

## 14.2 最小界面布局

### 左侧主图

- K 线 / footprint / heatmap（按现有能力）
- 事件 overlay
- anchor overlay
- episode segment overlay

### 右侧状态面板

必须显示：

1. 当前 top regimes
2. 当前 top event hypotheses
3. 当前 active anchors
4. missing confirmation
5. invalidating signals
6. transition watch
7. data freshness/completeness
8. degraded mode badge
9. profile version / engine version

### 下方 review 面板

必须显示：

- 已闭合 episode 列表
- episode evaluation
- failure mode 聚类
- AI tuning recommendation
- patch compare

## 14.3 UI 关键交互

1. 选择某个 episode → 显示完整生命周期
2. 查看某个 belief state → 展示当时 top hypotheses 与 active anchors
3. 切换 profile version → 对比同一 replay 的识别结果
4. 查看 patch candidate → 前后对比 episode 统计变化

---

# 15. 实施路线图

## Phase 0：主规格落地准备

目标：不写新花样，先把概念固定。

交付物：

- ontology constants
- schema definitions
- profile parameter registry
- evaluation enums

完成标准：

- 所有核心对象命名稳定
- 所有 JSON/YAML schema 可被 validate

## Phase 1：Append-only 观测与重建骨架

目标：确保任何衍生层都能从原始观测重建。

交付物：

- append-only observation tables
- rebuild command
- ingestion idempotency
- dead letter handling

完成标准：

- 删除衍生层后可重建 belief chain
- 重建结果 deterministic

## Phase 2：Deterministic Recognition Engine V1

目标：先把 3 类事件闭环跑通。

交付物：

- feature slice builder
- regime updater
- event hypothesis updater
- anchor manager
- belief state emitter
- event episode closer

完成标准：

- `momentum_continuation`
- `balance_mean_reversion`
- `absorption_to_reversal_preparation`

三类事件可形成 episode

## Phase 3：Episode Evaluation V1

目标：把 replay 结果转成调参友好的标准评估。

交付物：

- episode evaluation generator
- rule review engine
- human review override support
- review API

完成标准：

- 每个闭合 episode 都可生成 evaluation
- 至少能分类前述失败模式

## Phase 4：Replay Workbench Review UI

目标：让人能看懂系统当时为什么那样判断。

交付物：

- belief state panel
- episode panel
- evaluation panel
- patch compare panel

完成标准：

- 操作者可完成单 episode 复盘
- 可看 profile/version 差异

## Phase 5：AI Tuning Advisor V1

目标：让 AI 稳定给出可审计调参建议。

交付物：

- tuning input bundle builder
- AI tuning output schema
- patch candidate generator
- offline validator

完成标准：

- AI 输出结构化建议
- patch 需通过 offline replay compare

## Phase 6：Shadow Validation / Reliability Hardening

目标：进入更可靠的持续使用阶段。

交付物：

- golden replay suite
- degradation tests
- backfill tests
- profile rollback tools
- observability dashboard

完成标准：

- 改 patch 前后可做标准比较
- 降级模式行为稳定

---

# 16. 测试与验收口径

## 16.1 测试分层

### 单元测试

测试：

- feature calculations
- threshold logic
- anchor decay
- hypothesis phase transitions
- profile boundary validation

### 合同测试

测试：

- ingestion schema
- belief state schema
- episode evaluation schema
- tuning recommendation schema

### 集成测试

测试：

- ingest → recognize → episode → evaluation
- replay rebuild determinism
- patch candidate validation

### Golden Replay 测试

至少准备：

- trend continuation day
- balance chop day
- absorption reversal day
- fake breakout day
- degraded no depth day

## 16.2 最关键的验收标准

### A. Determinism

同一 replay + 同一 profile + 同一 engine version，应产生相同结果。

### B. Explainability

任何 belief state 必须能展示 supporting / missing / invalidating。

### C. Rebuildability

从原始观测可重建衍生层。

### D. Patch Safety

patch 未经验证不得上线。

### E. Degraded Continuity

AI、DOM、depth 任一不可用时，系统应降级继续运行。

## 16.3 Calibration 初版口径

`calibration_score` V1 不要求复杂统计校准，可先用规则近似：

- 高概率 episode 是否更常 materialize
- 高概率是否经常在短时间内被 invalidated
- 低概率但频繁兑现时是否说明模型偏保守

后续再升级成更正式的 calibration curves。

---

# 17. 运维与运行手册

## 17.1 启动顺序

1. 启动 storage / app server
2. 检查 schema registry
3. 加载 active instrument profiles
4. 启动 ingestion endpoints
5. 启动 recognition worker
6. 启动 replay workbench UI
7. 最后启动 AI tuning service（非关键路径）

## 17.2 异常场景处理

### 场景 A：adapter payload schema mismatch

动作：

- 写入 dead_letter_payload
- 标记 ingestion degraded
- 不允许 silently drop

### 场景 B：depth feed 中断

动作：

- recognition_mode → `degraded_no_depth`
- depth bucket 降权
- belief state 继续生成

### 场景 C：AI 服务不可用

动作：

- `ai_available = false`
- tuning API 返回 unavailable
- recognition 正常运行

### 场景 D：belief rebuild needed

动作：

- 标记 `rebuild_required`
- 执行 rebuild job
- 保留旧衍生结果与新结果对比

## 17.3 观测指标

至少记录：

- ingestion lag
- recognition lag
- rebuild duration
- episode close rate
- evaluation generation rate
- degraded mode duration
- AI recommendation success rate
- patch validation pass rate

---

# 18. 代码组织建议

在尽量复用现有仓库结构的前提下，建议新增或强化如下模块：

```text
src/
  atas_market_structure/
    app.py
    server.py
    models.py
    repository.py
    services.py

    ontology.py
    profile_registry.py
    schema_registry.py

    ingestion/
      adapter_ingest.py
      market_structure_ingest.py
      process_context_ingest.py
      depth_ingest.py

    recognition/
      feature_builder.py
      regime_updater.py
      event_updater.py
      anchor_manager.py
      belief_emitter.py
      episode_closer.py
      degraded_mode.py

    review/
      episode_evaluator.py
      rule_review.py
      human_override.py

    tuning/
      bundle_builder.py
      ai_recommendation_client.py
      patch_candidate.py
      patch_validator.py
      patch_promoter.py

    rebuild/
      rebuild_runner.py
      rebuild_compare.py

    api/
      health_api.py
      belief_api.py
      review_api.py
      tuning_api.py
      rebuild_api.py

schemas/
  observation/
  belief/
  episode/
  evaluation/
  tuning/
  profile/

samples/
  golden_replays/
  episode_evaluations/
  tuning_recommendations/
  profile_patches/

tests/
  unit/
  contract/
  integration/
  golden/
```

---

# 19. Codex 实施规则

以下规则是给 Codex 的明确约束，必须遵守：

## 19.1 不允许偏离主理念

不要把系统改回：

- 静态标签识别器
- 单指标触发器
- AI 自由发挥解释器

## 19.2 不要重写 ontology

- regime ontology 固定
- event ontology 固定
- phase ontology 固定
- evaluation ontology 固定

只允许在 profile 层加参数，不允许发明新的语义体系。

## 19.3 先建基础设施，再建 AI 协作

开发顺序不可颠倒：

1. schema
2. append-only observation
3. deterministic recognition
4. episode evaluation
5. UI/review
6. AI tuning advisor

## 19.4 所有新增功能必须带测试

每个模块至少配：

- 单元测试
- schema/contract 测试
- 一条 golden replay 相关测试

## 19.5 所有衍生对象必须带版本

任何以下对象如果没有 profile / engine version，视为不合格：

- belief state
- event episode
- episode evaluation
- tuning recommendation

## 19.6 所有 patch 都必须可回滚

任何参数变更都必须：

- 有 patch id
- 有前后 diff
- 有 validation result
- 有 promote / rollback 记录

---

# 20. 第一批实施任务清单

## Task 1：固定 ontology 与 enums

交付：

- `ontology.py`
- event/regime/phase/failure mode constants
- schema enum definitions

## Task 2：实现 `instrument_profile_v1` schema 与 registry

交付：

- YAML schema
- profile loader
- profile boundary validator

## Task 3：实现 `belief_state_snapshot` schema

交付：

- JSON schema
- sample belief states
- contract tests

## Task 4：实现 `event_episode` 与 `episode_evaluation_v1`

交付：

- schemas
- repository support
- rule review skeleton

## Task 5：实现 recognition engine V1 skeleton

交付：

- feature builder
- regime updater
- event updater
- anchor manager
- belief emitter
- episode closer

## Task 6：实现 rebuild runner

交付：

- replay rebuild command
- deterministic compare tool

## Task 7：实现 review API 与 UI 数据接口

交付：

- review endpoints
- belief/episode/evaluation endpoints

## Task 8：实现 tuning bundle builder 与 AI recommendation schema

交付：

- tuning input bundle
- AI output schema
- example recommendation

## Task 9：实现 patch candidate 与 offline validator

交付：

- patch diff generator
- offline replay compare
- validation result report

## Task 10：补齐 golden replay tests

交付：

- 至少 5 个 golden replay cases
- 结果对比基线

---

# 21. 对“高可用性”的现实说明

本规格的目标是 **最大化高可用性与识别稳定性**，但不能承诺绝对正确或绝对不中断。

本项目中的“高可用”应理解为：

- 可继续运行
- 可降级运行
- 可解释当前能力边界
- 可回放重建
- 可审计与回滚

而不是：

- 永远识别正确
- 永不漏报误报
- AI 永远给出最优调参

如果有人试图把“高可用”理解成“识别永远对”，这是错误目标。

正确目标是：

**让系统在面对不完整数据、复杂市场、规则迭代、AI 不确定性时，仍保持稳定、透明、可改进。**

---

# 22. 给 Codex 的主 Prompt（可直接使用）

下面这段可以直接发给 Codex 作为主任务指令：

```text
你正在接手一个 ATAS Replay Workbench / Event Model 项目。

请严格按照以下原则实施，不要自由改写核心理念：

1. 本项目不是静态事件标签识别器，而是“市场隐状态推断 + 事件假设跟踪 + 记忆锚点修正 + belief state 投影 + AI 调参与诊断协作系统”。
2. 必须严格分离 observed facts 与 derived interpretation。
3. 必须优先实现 deterministic recognition engine，AI 不是关键路径。
4. 必须把 Replay Workbench 的第一阶段范围收敛到 3 个 tradable events：
   - momentum_continuation
   - balance_mean_reversion
   - absorption_to_reversal_preparation
5. 必须固定 ontology：
   - regimes
   - event hypotheses
   - phases
   - failure modes
   不允许随意发明新的语义体系。
6. 必须实现以下核心对象与 schema：
   - instrument_profile_v1
   - belief_state_snapshot
   - event_episode
   - episode_evaluation_v1
   - tuning_recommendation
   - profile_patch_candidate
7. 所有识别与评估输出都必须带：
   - profile_version
   - engine_version
   - schema_version
8. 必须支持高可用与降级运行：
   - AI 不可用时 recognition 继续运行
   - depth/DOM 缺失时 recognition 降级而不是停止
   - 所有衍生层都必须可从 append-only 观测重建
9. 必须实现 replay rebuild、golden replay tests、patch offline validation。
10. 所有 patch 必须可回滚，不允许自动上线。

请按以下顺序施工：
A. 固定 ontology 与 schema
B. 建立 instrument_profile registry 与 boundary validator
C. 建立 belief_state / event_episode / episode_evaluation 数据模型
D. 实现 recognition engine skeleton
E. 实现 rebuild runner
F. 实现 review APIs
G. 实现 tuning bundle / AI recommendation / patch validation
H. 补齐 tests 与样例

输出要求：
- 每完成一个阶段，都给出：变更文件列表、设计说明、测试结果、未完成项、下一阶段建议
- 不要一次性大重构，优先小步提交
- 不要删除已有仓库中可复用的 ingestion / repository / adapter 基础设施
- 如果发现现有设计与主规格冲突，优先保留主规格中的 ontology、分层与高可用原则
```

---

# 23. 本规格是否足够开工

是。

这份 Master Spec v2 的目标，就是让 Codex 可以：

- 不再停留在理念理解层
- 不再迷失于自由发挥
- 不再把项目做回普通指标系统
- 直接进入分阶段、可测试、可回滚的连续实施

后续如果继续扩展，应采用“增量补充章节”方式，而不是推翻本规格。

