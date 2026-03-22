# Codex 实施说明书：Replay Workbench 的 AI 调参顾问与 Episode 评估体系

## 0. 这份文件的用途

这不是普通的“写几个指标”任务说明，而是给 Codex 的统一执行文档。

目标是让 Codex 按照 Replay Workbench 当前的核心理念，先落地一个 **可用、可审计、可回滚** 的 AI 调参顾问系统，而不是冒进做一个不可控的“自动在线自调参引擎”。

本文件整合了以下判断：

1. 这个方向是否真的可行
2. 为什么要先做 episode 评估，而不是先做 AI 自动调参
3. 第一阶段该做什么、不该做什么
4. 需要哪些 schema、对象、接口与日志
5. 给 Codex 的明确开发边界、优先级和交付清单

---

## 1. 项目共识：先统一世界观

### 1.1 本项目不是在做什么

本项目 **不是**：

- 静态事件标签识别器
- 从文本里抽几个术语和价位的摘要器
- 直接输出“看涨/看跌”的黑盒判断器
- 第一版就让 AI 替代底层状态机的收益预测器

### 1.2 本项目是在做什么

本项目是在做：

**市场隐状态推断 + 事件假设跟踪 + 记忆锚点修正 + 交易决策支持系统**

更口语化地说：

**我们交易的不是价格本身，而是“市场事件是否成立、是否继续、是否被否决”。**

### 1.3 最重要的设计原则

1. **事件不是标签，而是轨迹**
   - 要表达形成、发展、确认、减弱、失效、接管
   - 不能只存一个事件名

2. **市场不是无记忆的**
   - 旧平衡中心、旧累积中心、缺口边缘、启动点、高成交接受区、被套库存区都应留下结构记忆
   - 它们不是简单的支撑阻力，而是多角色锚点

3. **系统必须允许不确定**
   - “待确认”是正确输出，不是失败输出
   - 必须允许并行事件假设，而不是过早单结论

4. **DOM 是机制证据层，不是最终事件层**
   - DOM 主要提供 defense / withdrawal / refresh absorption / vacuum / migration / trade-through difficulty 等证据
   - 不能脱离历史锚点和大背景单独做方向结论

5. **当前 UI 常见对象属于投影层，不是底层认知模型**
   - `plan / zone / risk / price` 有价值
   - 但应被视为 belief state 的用户可操作投影，而不是底层建模本身

---

## 2. 对“AI 调参”这件事的结论

## 2.1 结论一句话

**能实现，但必须降目标。**

真正高可行、能做出来且有用的版本是：

- AI 读取结构化回放和 episode 日志
- 诊断当前系统是“确认太早 / 失效太晚 / 接管漏判”等哪类问题
- 给出参数修改建议
- 生成候选 patch
- 在离线评估通过后，再由人工或规则批准上线

### 2.2 可行性分级

#### 高可行：AI 调参顾问

可行性：**高**

AI 适合做：

- 读 episode 生命周期
- 看 validation / invalidation / replacement 的触发轨迹
- 总结失败模式
- 指出哪类参数最值得改
- 给出候选 patch 草案

#### 中等可行：AI 生成候选补丁 + 离线回测比较

可行性：**中等**

要求：

- 参数空间要收敛
- episode 评估要标准化
- 补丁生成后必须离线重跑评估
- 需要严格版本化与回滚能力

#### 低可行：AI 在线自动自调参

可行性：**低**

原因：

- 市场非平稳
- 真值不天然存在
- 目标不止收益，还包括校准、确认、失效、接管
- 容易过拟合最近样本
- 难审计、难回滚、难归因

### 2.3 为什么不能一上来就做“自动调参”

因为你的系统不是一个干净的监督学习问题。

它的难点在于：

1. **隐变量问题**
   - 你要判断的是 regime、event hypothesis、anchor interaction、phase
   - 这些不是天然可见标签

2. **多解等价问题**
   - 不同参数组合可能得到类似的表面结果
   - AI 很容易提出“也许可以”的方案，但未必是真正稳定解

3. **非平稳问题**
   - 不同品种、不同 session、不同波动环境，最佳节奏都可能变化

4. **多目标问题**
   - 目标不只是 PnL
   - 还包括概率校准、确认时机、失效时机、事件接管识别

5. **日志与评估决定上限**
   - 没有结构化 episode 生命周期记录，AI 再强也只能讲故事

---

## 3. 第一阶段的正确目标

第一阶段不追求：

- 自动赚钱
- 自动改线上参数
- 全品种全事件统一优化
- 用 AI 直接接管底层状态机

第一阶段只追求：

### 3.1 搭建一个 AI 调参顾问闭环

闭环如下：

1. 规则/状态引擎继续负责产出：
   - 当前 regime
   - top event hypotheses
   - phase
   - probability
   - supporting evidence
   - missing confirmation
   - invalidating signals
   - active memory anchors
   - replacement / downgrade 轨迹

2. 对已闭合 episode 生成标准化评估结果

3. AI 只读取这些结构化评估与轨迹日志

4. AI 输出：
   - diagnosis
   - parameter patch candidate
   - confidence

5. 补丁先离线评估，再决定是否采用

### 3.2 第一阶段只做三类事件

只聚焦：

1. `momentum_continuation`
2. `balance_mean_reversion`
3. `absorption_to_reversal_preparation`

原因：

- 这是最核心的三类交易脉络
- 覆盖“延续 / 回归 / 吸收到反转准备”三条主线
- 足够验证系统是否真的具备事件理解与调参能力

### 3.3 第一阶段只做三类失败模式

1. `early_confirmation`
2. `late_invalidation`
3. `missed_transition`

原因：

- 这三类直接对应最核心的三个能力：确认、失效、接管
- 它们都能稳定映射到具体参数，而不是抽象评价

---

## 4. 推荐系统架构

## 4.1 底层认知链路

推荐始终遵循以下链路：

```text
Observation -> FeatureSlice -> HiddenRegime posterior -> EventHypothesis posterior
-> MemoryAnchor / AnchorInteraction adjustment -> BeliefState -> Projection/UI/AI explanation
```

## 4.2 核心对象层级

至少保留以下对象：

1. `Observation`
2. `FeatureSlice`
3. `HiddenRegime`
4. `EventHypothesis`
5. `MemoryAnchor`
6. `AnchorInteraction`
7. `EventEpisode`
8. `BeliefState`
9. `EpisodeEvaluation`
10. `InstrumentProfile`
11. `TuningRecommendation`
12. `ParameterPatchCandidate`

## 4.3 角色分工

### 规则/状态引擎负责

- 底层状态更新
- 基本概率更新
- validation / invalidation / replacement 检查
- event episode 生命周期记录
- belief state 产出

### AI 负责

- 解释 belief state
- 总结 episode 为什么成功或失败
- 按失败模式归类
- 输出调参建议与候选 patch
- 协助生成复盘摘要

### 明确禁止

- AI 第一阶段直接承担无约束底层概率更新
- AI 第一阶段直接热更新线上参数
- AI 直接把收益最大化当成唯一目标

---

## 5. 先做 episode 评估，而不是先做 AI 自动调参

这是整个方案里最关键的一点。

没有统一的 episode 评估，AI 后续所有“调参建议”都只是听起来聪明的话。

有了评估表后，AI 才能真正做工程诊断。

### 5.1 评估目标

`EpisodeEvaluation` 评估的不是交易盈亏本身，而是：

1. 主事件猜得对不对
2. 确认时机是否合理
3. 失效降级是否及时
4. 新事件接管是否识别到
5. 概率是否有校准意义

### 5.2 v1 评分维度

建议 5 个维度，评分区间为 `-2 / -1 / 0 / +1 / +2`：

1. `hypothesis_selection_score`
2. `confirmation_timing_score`
3. `invalidation_timing_score`
4. `transition_handling_score`
5. `calibration_score`

### 5.3 v1 最小字段草案

```json
{
  "episode_id": "string",
  "instrument": "ES|NQ|GC|CL",
  "session": "RTH|ETH",
  "bar_tf": "1m|5m",
  "market_time_start": "iso8601",
  "market_time_end": "iso8601",
  "profile_version": "string",
  "schema_version": "episode_evaluation_v1",

  "initial_regime_top1": "string",
  "initial_regime_prob": 0.0,
  "evaluated_event_kind": "string",
  "initial_phase": "emerging|building|confirming|weakening|resolved|invalidated",
  "initial_prob": 0.0,
  "declared_time_window": {
    "mode": "next_5_bars|next_15m|custom",
    "bars_max": 5
  },
  "anchor_context": ["string"],

  "lifecycle": {
    "started_at": "iso8601",
    "first_validation_hit_at": "iso8601|null",
    "peak_prob": 0.0,
    "peak_prob_at": "iso8601|null",
    "first_invalidation_hit_at": "iso8601|null",
    "downgraded_at": "iso8601|null",
    "resolved_at": "iso8601|null",
    "resolution": "confirmed|invalidated|expired|replaced|partial",
    "replacement_event": "string|null"
  },

  "outcome": {
    "did_event_materialize": true,
    "did_partial_materialize": false,
    "dominant_final_event": "string",
    "judgement_source": "rule_review_v1|human_review_v1"
  },

  "scores": {
    "hypothesis_selection_score": 0,
    "confirmation_timing_score": 0,
    "invalidation_timing_score": 0,
    "transition_handling_score": 0,
    "calibration_score": 0
  },

  "diagnosis": {
    "primary_failure_mode": "early_confirmation|late_invalidation|missed_transition|none",
    "supporting_reasons": ["string"],
    "missing_confirmation": ["string"],
    "invalidating_signals_seen": ["string"]
  },

  "tuning_hints": {
    "candidate_parameters": ["string"],
    "suggested_direction": {
      "param_name": "increase|decrease|hold"
    },
    "confidence": "low|medium|high"
  }
}
```

### 5.4 评分含义示例

#### `hypothesis_selection_score`
- `+2`：主事件就是它
- `+1`：主事件基本对，但有竞争事件
- `0`：模糊
- `-1`：偏错
- `-2`：完全错

#### `confirmation_timing_score`
- `+2`：确认时机很好
- `+1`：略早或略晚但可接受
- `0`：一般
- `-1`：明显过早或过晚
- `-2`：严重错误

#### `invalidation_timing_score`
- `+2`：失效判定及时
- `+1`：稍慢但可接受
- `0`：一般
- `-1`：明显迟钝
- `-2`：旧事件该退出却长期占主导

#### `transition_handling_score`
- `+2`：及时识别新事件接管
- `+1`：略慢但识别到了
- `0`：模糊
- `-1`：识别很慢
- `-2`：完全没识别接管

#### `calibration_score`
- `+2`：高概率更常兑现，低概率更常不兑现
- `+1`：大体匹配
- `0`：一般
- `-1`：明显偏乐观或偏保守
- `-2`：概率缺乏校准意义

---

## 6. Instrument Profile：统一事件语言，参数按品种分层

## 6.1 原则

不要给每个品种发明一套不同的事件语言。

正确做法：

- **共用事件 ontology**
- **按品种维护 instrument profile**

也就是：

- 事件语义层统一
- 参数层可调

## 6.2 不该按品种变化的内容

以下内容应尽量统一：

- regime 主分类
- event hypothesis 主语义
- memory anchor 类型
- event template 骨架字段

## 6.3 该按品种调整的内容

以下内容应进入 `InstrumentProfile`：

1. **时间窗参数**
2. **validation / invalidation 阈值**
3. **DOM / anchor / path dependency 等证据权重**
4. **记忆锚点衰减参数**
5. **replacement / downgrade 逻辑参数**
6. **不同 session 的特殊节奏配置**

## 6.4 推荐 profile 结构

```yaml
instrument: NQ
profile_version: nq_profile_v0.1.0

normalization:
  tick_size: 0.25
  price_scale_mode: ticks
  atr_window: 20

regime_priors:
  strong_momentum_trend: 0.18
  weak_momentum_trend_narrow: 0.16
  weak_momentum_trend_wide: 0.14
  balance_mean_reversion: 0.24
  compression: 0.14
  transition_exhaustion: 0.14

time_windows:
  momentum_continuation:
    strong:
      bars_min: 2
      bars_max: 8
    normal:
      bars_min: 3
      bars_max: 12
  balance_mean_reversion:
    default:
      bars_min: 4
      bars_max: 20
  absorption_to_reversal_preparation:
    default:
      bars_min: 3
      bars_max: 15

thresholds:
  momentum_continuation:
    min_relaunch_displacement_ticks: 16
    max_retrace_ratio_before_downgrade: 0.52
    old_balance_return_penalty_trigger: 0.65
  balance_mean_reversion:
    center_reclaim_score_trigger: 0.60
  absorption_to_reversal_preparation:
    absorption_strength_trigger: 0.68
    follow_through_deadline_bars: 6

weights:
  dom_evidence: 0.85
  anchor_influence: 1.10
  path_dependency: 1.00
  price_structure: 1.20

decay:
  balance_center_half_life_bars: 120
  gap_edge_half_life_bars: 80
  initiative_origin_half_life_bars: 60

replacement_logic:
  momentum_continuation_to_balance_mean_reversion_score: 0.70
  momentum_continuation_to_reversal_preparation_score: 0.78
```

---

## 7. AI 调参顾问：输入与输出契约

## 7.1 AI 输入

AI 不应该直接读原始所有数据自由发挥。

第一阶段 AI 的输入应为结构化对象：

1. 当前 `InstrumentProfile`
2. 最近 N 个已闭合 `EpisodeEvaluation`
3. 对应 `EventEpisode` 生命周期摘要
4. 每类失败模式的统计摘要
5. 最近几次 profile 修改历史
6. 选定样本的成功案例与失败案例对照

可选：

- 对应 belief state 快照摘要
- 关键 anchor interaction 摘要

## 7.2 AI 输出

AI 输出必须收敛成固定格式，不允许散文化胡乱发挥。

```json
{
  "recommendation_id": "string",
  "instrument": "NQ",
  "profile_version": "nq_profile_v0.1.0",
  "target_event": "momentum_continuation",
  "primary_failure_mode": "early_confirmation",
  "diagnosis_note": "最近 40 个 episode 的主要问题不是方向错，而是确认太早。多数失败样本在规定窗口内没有第二次 initiative，却仍维持高概率。",
  "candidate_parameters": [
    "time_windows.momentum_continuation.strong.bars_max",
    "weights.dom_evidence",
    "thresholds.momentum_continuation.old_balance_return_penalty_trigger"
  ],
  "suggested_changes": {
    "time_windows.momentum_continuation.strong.bars_max": {
      "action": "decrease",
      "from": 8,
      "to": 6
    },
    "weights.dom_evidence": {
      "action": "decrease",
      "from": 0.85,
      "to": 0.75
    },
    "thresholds.momentum_continuation.old_balance_return_penalty_trigger": {
      "action": "decrease",
      "from": 0.65,
      "to": 0.55
    }
  },
  "expected_benefit": [
    "减少强动能延续的过早确认",
    "降低仅靠 DOM 推进但无位移转化的假阳性",
    "更快识别回到旧 balance 后的延续失效"
  ],
  "risk_notes": [
    "可能增加晚确认风险",
    "可能降低某些快速单边日的捕捉率"
  ],
  "confidence": "medium"
}
```

## 7.3 明确禁止的 AI 行为

- 不允许 AI 改 ontology
- 不允许 AI 自发增加几十个新参数
- 不允许 AI 直接覆盖线上 profile
- 不允许 AI 只看 PnL 做结论
- 不允许 AI 跨品种无差别复用 patch

---

## 8. 补丁评估流程

## 8.1 推荐流程

```text
Current Profile
-> Run episodes / evaluations
-> AI diagnosis
-> Generate patch candidate
-> Offline replay re-evaluation
-> Compare metrics
-> Human/rule approval
-> New profile version
```

## 8.2 补丁通过条件（建议）

候选 patch 至少要满足：

1. 目标失败模式显著改善
2. 不能明显恶化其它核心维度
3. `calibration_score` 不能变差太多
4. 不能让 replacement/transition 处理明显变钝
5. 要有 profile version、patch id、change log

---

## 9. 需要新增或补齐的模块

## 9.1 Schema

Codex 需要补齐以下 schema：

1. `episode_evaluation_v1.json`
2. `instrument_profile_v1.json` 或 `yaml schema`
3. `tuning_recommendation_v1.json`
4. `parameter_patch_candidate_v1.json`
5. `event_episode_summary_v1.json`

## 9.2 评估器

新增 `episode evaluator`：

输入：
- `EventEpisode`
- `BeliefState` snapshots
- current `InstrumentProfile`

输出：
- `EpisodeEvaluation`

### evaluator v1 只负责

- 三类事件
- 三类失败模式
- 五个评分维度

## 9.3 汇总器

新增 `evaluation aggregator`：

输入：
- 一批 `EpisodeEvaluation`

输出：
- 按事件类型统计
- 按失败模式统计
- 按 instrument / session 统计
- 参数影响线索摘要

## 9.4 AI 调参接口

新增一个只读分析接口，例如：

- `POST /tuning/recommendations/generate`
- `GET /tuning/recommendations/{id}`
- `POST /tuning/patches/evaluate`

第一阶段这个接口只产生候选建议，不直接部署。

---

## 10. 开发优先级

### P0：必须先做

1. `EpisodeEvaluation` schema
2. evaluator v1
3. instrument profile schema
4. evaluation aggregator
5. tuning recommendation schema
6. patch candidate schema

### P1：紧接着做

1. 最小 CLI 或 API 生成调参建议输入包
2. AI recommendation prompt/runtime
3. 离线 patch compare 工具
4. profile version / patch history

### P2：后做

1. UI 展示 tuning recommendation
2. 可视化失败模式分布
3. 半自动 patch 审批流

### 暂不做

1. 在线自动热更新 profile
2. 全事件全集合调参
3. 全品种统一自动学习
4. 以收益为唯一目标的黑盒优化器

---

## 11. 对 Codex 的明确工程要求

### 11.1 工程原则

1. 不要发明新的宏大概念
2. 先做最小闭环
3. 先支持三类事件与三类失败模式
4. 一切对象要可版本化
5. 一切建议要可审计、可回滚
6. 先保守，再扩展

### 11.2 命名要求

- 使用明确、稳定、可读的 schema 名称
- 避免临时魔法字符串
- 所有枚举集中定义
- 所有 patch 都要带 `from / to / action / reason`

### 11.3 数据原则

- Observation 层 append-only
- EpisodeEvaluation 为衍生层，不覆盖原始 episode
- AI recommendation 为建议层，不覆盖 profile
- patch evaluation 结果要和 patch candidate 分离存储

### 11.4 评估原则

- 不以 PnL 作为唯一或第一评价标准
- 重点看：确认、失效、接管、校准
- 每个建议必须说明会改善哪类错误，也必须说明风险

---

## 12. 建议目录结构

```text
schemas/
  episode_evaluation_v1.json
  instrument_profile_v1.json
  tuning_recommendation_v1.json
  parameter_patch_candidate_v1.json
  event_episode_summary_v1.json

src/
  evaluation/
    episode_evaluator.py
    scoring.py
    failure_modes.py
    aggregation.py
  tuning/
    recommendation_service.py
    patch_compare.py
    profile_loader.py
    patch_history.py
  prompts/
    tuning_recommendation_prompt.md

config/
  instruments/
    ES.yaml
    NQ.yaml
    GC.yaml
    CL.yaml

tests/
  evaluation/
  tuning/
```

---

## 13. 第一阶段的验收标准

只有满足下面条件，才算第一阶段真的可用：

1. 能针对三类事件生成 `EpisodeEvaluation`
2. 能稳定区分三类主要失败模式
3. 能按 instrument profile 输出结构化 tuning recommendation
4. 能生成 patch candidate，并离线比较前后评分变化
5. 结果可以回溯到：
   - 哪些 episode
   - 哪些失败模式
   - 哪些参数
   - 为什么建议改
6. 任何 patch 都不会自动线上生效

---

## 14. 给 Codex 的主 Prompt

下面这段可以直接作为 Codex 的主任务指令使用。

---

# Codex 主 Prompt

你正在为 `atas-market-structure` 项目实现一个 **Replay Workbench AI 调参顾问 v1**。

## 目标

不要实现“自动在线调参器”。

请实现一个 **可审计、可回滚、以 episode 评估为核心的离线调参建议系统**。

## 项目理念与边界

请严格遵守以下理念：

1. 本项目不是静态事件标签识别器，而是市场隐状态推断 + 事件假设跟踪 + 记忆锚点修正系统。
2. 事件不是标签，而是轨迹；必须考虑 phase、probability、validation、invalidation、replacement。
3. DOM 是机制证据层，不是最终事件层。
4. `plan / zone / risk / price` 是投影层，不是底层认知模型。
5. 第一版不允许 AI 直接替代底层状态机，也不允许自动上线参数。

## 实现范围

第一阶段只支持：

### 事件
- `momentum_continuation`
- `balance_mean_reversion`
- `absorption_to_reversal_preparation`

### 失败模式
- `early_confirmation`
- `late_invalidation`
- `missed_transition`

### 评分维度
- `hypothesis_selection_score`
- `confirmation_timing_score`
- `invalidation_timing_score`
- `transition_handling_score`
- `calibration_score`

## 你要完成的工作

1. 定义并实现 `episode_evaluation_v1` schema
2. 实现 `EpisodeEvaluator`，从 event episode / belief state / profile 生成 evaluation
3. 定义并实现 `instrument_profile_v1` schema
4. 定义并实现 `tuning_recommendation_v1` schema
5. 定义并实现 `parameter_patch_candidate_v1` schema
6. 实现 evaluation aggregation
7. 实现一个生成 AI 调参建议输入包的服务或脚本
8. 实现离线 patch compare 工具
9. 为以上模块编写测试
10. 写最小 README 或开发说明，说明如何运行 evaluator 与 patch compare

## 明确禁止

不要做以下事情：

- 不要实现在线自动 profile 热更新
- 不要把 PnL 当成唯一目标函数
- 不要扩展到全事件全集合
- 不要让 AI 自由发明 ontology 或大量新参数
- 不要删除现有 belief-state / event-episode 的可解释性

## 设计要求

1. 所有 schema 必须版本化
2. 所有 patch 必须可审计、可回滚
3. 所有 recommendation 必须包含：
   - diagnosis_note
   - candidate_parameters
   - suggested_changes
   - expected_benefit
   - risk_notes
   - confidence
4. 所有 evaluator 输出必须包含：
   - lifecycle
   - outcome
   - scores
   - diagnosis
   - tuning_hints
5. 参数变更必须使用 `from -> to` 明确表达

## 目录建议

优先使用以下目录：

- `schemas/`
- `src/evaluation/`
- `src/tuning/`
- `config/instruments/`
- `tests/evaluation/`
- `tests/tuning/`

## 交付要求

你的输出应优先形成一个最小闭环：

`profile -> episode -> evaluation -> aggregated diagnosis -> recommendation -> patch compare`

在实现过程中，始终遵守“先做可用闭环，再做扩展”的原则。

---

## 15. 最后一句话

这个项目第一阶段最有价值的，不是“让 AI 自动调参”，而是：

**把 Replay Workbench 变成一个能稳定记录、评估、解释事件生命周期，并据此提出高质量调参建议的系统。**

只有这一步做好了，后面的半自动优化、跨品种 profile 演进，才有基础。
