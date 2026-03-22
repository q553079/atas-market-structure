# Codex 多线程实施计划与详细 Prompt（基于 Replay Workbench Master Spec v2）

状态：可直接执行  
适用对象：Codex 多线程并行开发  
目标：在不破坏现有仓库结构的前提下，按完整蓝图推进 **高可用事件识别 + 高可用 AI 调参与诊断协作系统**。

---

# 1. 总体建议：不要无脑全并行

你虽然可以开很多 Codex 线程，但这个项目不是“线程越多越快”。

最优方案不是 15～20 个线程乱跑，而是：

**总共 10 个线程**，其中：
- **1 个总集成线程**
- **8 个功能实施线程**
- **1 个测试/回放/验收线程**

但执行时要分 **3 个波次（waves）**，任意时刻建议并行 **不超过 5 个线程**。

否则会出现：
- schema 冲突
- migration 冲突
- recognition / evaluation / tuning contract 不一致
- UI 读取旧字段
- 多个线程重复造轮子

---

# 2. 推荐线程划分

## Thread 00 — 总集成 / 守门线程
职责：
- 读取 Master Spec v2 与现有仓库
- 建立任务台账、目录接缝、实施顺序
- 审核其他线程的输出是否符合统一 ontology / schema / HA 原则
- 最后负责集成、冲突解决、统一文档

## Thread 01 — Schema / Contract 线程
职责：
- 建立所有核心 schema 与枚举
- 固化 ontology、episode evaluation、AI tuning I/O contract
- 输出 JSON Schema / YAML Schema / 示例 payload

## Thread 02 — Storage / Migration 线程
职责：
- 落地 SQLite/WAL、表结构、索引、版本化与 append-only 规则
- 实现 migrations 与 rebuild 所需基础设施

## Thread 03 — Ingestion / Reliability 线程
职责：
- 构建 ingestion plane
- schema validation、幂等写入、dead letter、health、degraded 状态
- 保证 AI 不在关键路径上

## Thread 04 — Recognition Engine 线程
职责：
- 落地 deterministic recognition skeleton
- feature slices、regime posterior、event hypotheses、belief state、episodes
- 支持 data completeness / degraded mode / transition watch

## Thread 05 — Instrument Profile / Parameter Boundary 线程
职责：
- 落地 instrument_profile_v1
- 参数边界、默认值、安全门、patch compare/validate 基础能力

## Thread 06 — Episode Evaluation 线程
职责：
- 构建 episode_evaluation_v1 生成逻辑
- 失败模式分类、评分维度、rule_review_v1 / hybrid review 接口

## Thread 07 — AI Tuning 线程
职责：
- 构建 tuning input bundle、tuning recommendation、patch candidate contract
- 实现离线 AI 调参协作层，严格非关键路径

## Thread 08 — Replay Workbench API / UI Projection 线程
职责：
- 面向 replay/review/workbench 的读取 API 与 projection 输出
- 显示 belief state、episodes、evaluations、recommendations、degraded badges

## Thread 09 — Golden Cases / Tests / Rebuild / CI 线程
职责：
- 建 golden replay cases
- 建 rebuild CLI / offline validation harness
- 构建 integration tests / regression tests / acceptance suite

---

# 3. 推荐执行波次

## Wave 0（先启动）
- Thread 00

## Wave 1（基础层）
- Thread 01
- Thread 02
- Thread 03
- Thread 04

## Wave 2（建立可评估闭环）
- Thread 05
- Thread 06
- Thread 07

## Wave 3（投影、回放、验收）
- Thread 08
- Thread 09
- Thread 00 负责收口集成

---

# 4. 统一约束（所有线程都要遵守）

把下面这段作为每个 Codex 线程 prompt 的共同前置要求。

## Shared Global Prompt

你正在修改仓库 `q553079/atas-market-structure`。本次工作必须以仓库中的 `replay_workbench_master_spec_v2.md` 为唯一主规格书，并兼容现有目录：`docs/`, `schemas/`, `samples/`, `scripts/`, `src/`, `src-csharp/`, `tests/`。

必须遵守以下硬约束：

1. 不要把项目做成自动交易系统。
2. 不要引入 AI 线上热更新参数。
3. 不要让 AI 进入识别关键路径。
4. 不要修改固定 ontology：regime / event hypothesis / phase / evaluation ontology 必须保持稳定。
5. observed facts 与 derived interpretation 必须严格分离。
6. observations、feature slices、posteriors、belief states、episodes、episode evaluations 必须保持 append-only 设计。
7. instrument profile、recognizer build、memory anchor freshness 等可变对象必须版本化。
8. depth/DOM 缺失时必须降级运行，而不是报错终止。
9. 所有关键输出都要带 `profile_version`、`engine_version`、`schema_version`，并尽可能带 `data_status` / `freshness` / `completeness`。
10. V1 只要求闭环三类可交易事件：
   - `momentum_continuation`
   - `balance_mean_reversion`
   - `absorption_to_reversal_preparation`
11. 任何新建模块都优先放到现有仓库结构中；如果目录不存在，可以创建，但不要大幅重构全仓。
12. 先扫描现有代码，尽量复用已有对象、已有 API、已有脚本，不要另起炉灶。
13. 写出清晰的 docstrings、类型标注、测试、示例 payload。
14. 所有实现必须可回放、可重建、可测试。
15. 任何设计选择若与 Master Spec v2 冲突，优先服从 Master Spec v2。

工作方式要求：
- 先做 repo scan，列出你将复用的现有文件和你要新增/修改的文件。
- 然后提交 implementation plan。
- 再开始改代码。
- 最终输出：
  1. 改了哪些文件
  2. 为什么这么改
  3. 哪些点仍是 TODO
  4. 如何运行/测试
  5. 风险与后续建议

不要泛泛而谈。直接在仓库内实施。

---

# 5. 线程之间的文件边界（尽量减少冲突）

## Thread 00
主改：
- `docs/implementation/`
- `docs/adr/`
- 根目录实施说明与集成文档

## Thread 01
主改：
- `schemas/`
- `samples/contracts/`
- `docs/contracts/`

## Thread 02
主改：
- `src/storage/` 或现有 backend storage 模块
- `scripts/migrations/`
- `docs/storage/`

## Thread 03
主改：
- `src/api/ingest/`
- `src/ingestion/`
- `src/ops/health/`
- `docs/ops/`

## Thread 04
主改：
- `src/recognition/`
- `src/features/`
- `src/belief/`
- `docs/recognition/`

## Thread 05
主改：
- `src/profiles/`
- `schemas/profiles/`
- `samples/profiles/`
- `docs/profiles/`

## Thread 06
主改：
- `src/evaluation/`
- `schemas/evaluation/`
- `samples/evaluations/`
- `docs/evaluation/`

## Thread 07
主改：
- `src/ai_tuning/`
- `schemas/tuning/`
- `samples/tuning/`
- `docs/tuning/`

## Thread 08
主改：
- `src/api/review/`
- `src/workbench/`（若已有则复用）
- `docs/workbench/`

## Thread 09
主改：
- `tests/`
- `samples/golden_cases/`
- `scripts/rebuild/`
- `scripts/validate/`
- CI 配置文件

---

# 6. 每个线程的详细 Prompt

下面每个 Prompt 都已经按“可直接复制给 Codex”来写。

---

## Thread 00 Prompt — 总集成 / 守门线程

你是本仓库本轮实施的总集成线程。你的任务不是大面积写业务代码，而是做“架构守门 + 任务台账 + 集成收口”。

先完整阅读：
- `replay_workbench_master_spec_v2.md`
- `README.md`
- `docs/architecture.md`
- `docs/replay_workbench_event_model/` 下所有文档
- 当前 `src/`, `schemas/`, `scripts/`, `tests/` 的现有结构

你的目标：
1. 输出一份 repo scan，总结现有代码与 Master Spec v2 的接缝。
2. 建立实施台账：
   - 哪些模块已存在
   - 哪些模块缺失
   - 哪些目录建议新增
   - 各线程建议触达哪些文件
3. 建立 ADR/决策记录，至少包括：
   - observed vs derived 分离原则
   - append-only 与 versioned state 边界
   - AI 非关键路径原则
   - degraded mode 设计原则
4. 建立集成检查清单，供其他线程完成后统一验收。
5. 在最后阶段，负责合并并统一文档、命名、版本字段、目录结构。

硬约束：
- 不要改动 ontology。
- 不要把自己变成另一个 feature 线程。
- 优先写文档、任务台账、ADR、集成 checklist、接口协调说明。

交付物至少包括：
- `docs/implementation/repo_gap_analysis.md`
- `docs/implementation/multi_thread_execution_plan.md`
- `docs/adr/ADR-001-observed-vs-derived.md`
- `docs/adr/ADR-002-append-only-and-versioned-state.md`
- `docs/adr/ADR-003-ai-not-on-critical-path.md`
- `docs/implementation/integration_acceptance_checklist.md`

请直接在仓库内实施。

---

## Thread 01 Prompt — Schema / Contract 线程

你负责本项目的统一 schema 与 contract 落地。目标是把 Master Spec v2 里的核心对象变成可校验、可复用、可示例化的 schema 契约。

先阅读：
- `replay_workbench_master_spec_v2.md`
- `docs/replay_workbench_event_model/` 全部文档
- `schemas/` 现有内容
- 与 ingestion / review / snapshot 相关的现有 schema 与 sample

请实现以下内容：

1. 固化 ontology 常量与枚举：
   - regime ontology（6 个）
   - event hypothesis ontology（8 个）
   - tradable event v1（3 个）
   - phase ontology（6 个）
   - evaluation failure modes v1
   - degraded mode enums

2. 为以下对象编写 JSON Schema 或等价 schema：
   - `belief_state_snapshot`
   - `event_episode`
   - `episode_evaluation_v1`
   - `instrument_profile_v1`
   - `tuning_input_bundle_v1`
   - `tuning_recommendation_v1`
   - `profile_patch_candidate_v1`
   - `patch_validation_result_v1`
   - `health_status_v1`
   - `data_status_v1`

3. 为每个 schema 提供：
   - 最小示例 payload
   - 正常示例
   - 降级示例（如 `degraded_no_depth`, `degraded_no_ai`）

4. 输出一份统一 contract 文档，明确：
   - 必填字段
   - 版本字段
   - 时间字段格式
   - ID 命名建议
   - 枚举定义

实施要求：
- 尽量复用现有 schema 目录风格。
- 如果仓库已有 validation helper，直接接入。
- 所有 schema 必须能用于程序校验。
- 不要混淆 observed facts 与 derived interpretation。
- `episode_evaluation_v1` 与 `instrument_profile_v1` 必须尽量贴合 Master Spec 示例。

交付物至少包括：
- `schemas/ontology/*.json` 或等价文件
- `schemas/contracts/*.json`
- `samples/contracts/*.json`
- `docs/contracts/core_contracts.md`
- 对应 schema validation tests

最终请输出：
- 你新增/修改的 schema 列表
- schema 之间的依赖关系
- 与其他线程的对接注意事项

请直接在仓库内实施。

---

## Thread 02 Prompt — Storage / Migration 线程

你负责把 Master Spec v2 的存储蓝图落地为可运行的本地存储层。V1 以 SQLite 为主，但必须遵守 WAL、append-only、versioned state、可 rebuild 的原则。

先阅读：
- `replay_workbench_master_spec_v2.md`
- 仓库中现有数据库/持久化/模型代码
- 现有 ingestion/review API 如何存储数据

请实现以下内容：

1. 设计并落地 SQLite schema / migration，至少覆盖：
   - 原始观测层：`observation_*`
   - 特征层：`feature_slice`
   - 状态层：`regime_posterior`, `event_hypothesis_state`, `belief_state_snapshot`, `projection_snapshot`
   - 记忆层：`memory_anchor`, `memory_anchor_version`, `anchor_interaction`
   - 轨迹层：`event_episode`, `event_episode_evidence`
   - 评估与调参层：`episode_evaluation`, `tuning_recommendation`, `profile_patch_candidate`, `patch_validation_result`
   - 版本与运维层：`instrument_profile`, `recognizer_build`, `ingestion_run_log`, `rebuild_run_log`, `dead_letter_payload`, `schema_registry`

2. 明确哪些表 append-only，哪些表 versioned。

3. 实现 migration runner：
   - 首次初始化
   - 升级迁移
   - migration 版本记录

4. 建立基础 repository / DAO 层，要求：
   - typed models
   - 幂等写入支持（至少对 ingestion payload 提供 dedupe 钩子）
   - 按 `instrument + market_time` 的高频读取支持

5. 为 rebuild 准备接口：
   - 能从 observation 重新生成衍生层
   - 至少预留 clear-derived-and-rebuild 的安全入口

实施要求：
- 不要破坏现有运行链路。
- 如果已有数据库模块，优先在现有基础上扩展。
- 必须加索引。
- 必须写 migration tests。
- 必须写 append-only / versioned state 的注释文档。

交付物至少包括：
- migrations 文件
- 存储模型与 repository 层
- `docs/storage/storage_blueprint.md`
- `docs/storage/table_lifecycle_rules.md`
- 基础 DB tests

请直接在仓库内实施。

---

## Thread 03 Prompt — Ingestion / Reliability 线程

你负责 ingestion plane 与高可用可靠性。目标是：即使 recognition/AI 暂时不可用，原始观测仍能安全入库，系统可健康报告，并支持 degraded mode。

先阅读：
- `replay_workbench_master_spec_v2.md`
- 现有 `src` 中的 API/ingestion/backend 代码
- 当前 `/health` 与 replay workbench 启动链路

请实现以下内容：

1. 梳理并落地以下 ingestion endpoints（如果已有则增强，不要重写）：
   - `POST /api/v1/ingest/market-structure`
   - `POST /api/v1/ingest/event-snapshot`
   - `POST /api/v1/ingest/process-context`
   - `POST /api/v1/ingest/depth-snapshot`
   - `POST /api/v1/ingest/adapter-payload`

2. 每个 endpoint 必须支持：
   - schema validation
   - 持久化原始 payload
   - 失败进入 dead letter
   - 幂等/重复提交保护（至少基于 payload hash 或 request id）
   - 标准错误响应

3. 实现 health/status 体系：
   - `healthy`
   - `degraded`
   - `rebuild_required`
   - `paused`
   - 明确 degraded reason：`degraded_no_depth`, `degraded_no_dom`, `degraded_no_ai`, `degraded_stale_macro`, `replay_rebuild_mode`

4. 输出 data completeness / freshness 状态基础字段，供 recognition / UI 使用。

5. 实现基础 run log / ingestion metrics。

6. 补齐 ops 文档：
   - dead letter 处理方式
   - health endpoint 示例
   - degrade 触发条件说明

硬约束：
- AI 不在关键路径上。
- 原始观测必须先落盘，再触发下游处理。
- depth/DOM 缺失不能导致 ingest 失败。
- 不要引入复杂消息队列，优先保持本地简单可靠。

交付物至少包括：
- ingestion handlers / services
- health/status endpoints
- dead letter 机制
- `docs/ops/ingestion_reliability.md`
- 对应 API tests

请直接在仓库内实施。

---

## Thread 04 Prompt — Recognition Engine 线程

你负责 deterministic recognition plane 的第一版骨架实现。目标是：在没有 AI 的情况下，系统能从 observations 产出 feature slices、regime posterior、event hypotheses、belief state、event episodes，并支持 degraded mode。

先阅读：
- `replay_workbench_master_spec_v2.md`
- `docs/replay_workbench_event_model/` 下所有文档
- 现有 src 中与 market structure / review / recognition 相关的代码

请实现以下内容：

1. recognition pipeline 主流程：
   - observations -> feature slices
   - feature slices -> regime posterior
   - regime posterior + evidence -> event hypothesis states
   - hypothesis states + anchors -> belief state snapshot
   - hypothesis lifecycle -> event episode

2. V1 只要求闭环这三类 tradable event：
   - `momentum_continuation`
   - `balance_mean_reversion`
   - `absorption_to_reversal_preparation`

3. evidence bucket 设计至少覆盖：
   - bar structure evidence
   - volatility/range evidence
   - trend efficiency evidence
   - initiative evidence
   - balance evidence
   - absorption evidence
   - depth/DOM evidence
   - anchor interaction evidence
   - path dependency evidence

4. 实现 degraded recognition：
   - 无 depth/DOM 时继续运行，但降低相关 evidence 权重并标记 unavailable
   - 宏观背景 stale 时加入 staleness penalty
   - 输出 `recognition_mode`

5. 为 belief state snapshot 输出至少以下内容：
   - top 3 regime probabilities
   - top 3 event hypotheses
   - active anchors
   - missing confirmation
   - invalidating signals seen
   - transition watch
   - data status / completeness / freshness
   - profile_version / engine_version

6. 形成 event episode：
   - phase 生命周期
   - resolution
   - replacement event
   - key evidence summary

硬约束：
- 识别结果必须 deterministic。
- AI 不能参与这条链路。
- 不要做“万能评分模型”，先用清晰的规则骨架和可调参数接口。
- 不要超出 V1 的三类事件闭环。
- 一定要保留多假设并行和 transition watch，不要强行单标签。

交付物至少包括：
- recognition modules
- belief state builder
- event episode builder
- `docs/recognition/recognition_pipeline_v1.md`
- 至少 3 组样例结果
- 对应单元测试

请直接在仓库内实施。

---

## Thread 05 Prompt — Instrument Profile / Parameter Boundary 线程

你负责 instrument profile、参数边界、安全门、profile patch 的基础设施。目标是：保持统一 ontology，不同品种只通过 profile 调 tempo/threshold/weights/decay/priors。

先阅读：
- `replay_workbench_master_spec_v2.md`
- `docs/replay_workbench_event_model/` 全部文档
- 仓库中与参数、配置、样例 profile 有关的代码

请实现以下内容：

1. 落地 `instrument_profile_v1`：
   - ontology_version
   - normalization
   - time_windows
   - thresholds
   - weights
   - decay
   - priors
   - safety

2. V1 先提供最小 profile 示例：
   - `ES.yaml`
   - `NQ.yaml`
   - 如果合理，可再给 `GC.yaml` / `CL.yaml` stub

3. 为每个可调参数建立 metadata：
   - `min`
   - `max`
   - `step`
   - `safe_default`
   - `criticality`
   - `applies_to_events`

4. 实现 patch candidate / boundary validation 基础逻辑：
   - 非法参数拒绝
   - 越界参数拒绝
   - ontology 字段不可改
   - `allow_ai_auto_apply: false`

5. 输出 compare/preview 能力：
   - 旧 profile vs 新 patch
   - 改了哪些字段
   - 风险提示

硬约束：
- ontology 固定，profile 只管参数。
- 不要把 profile 做成“任意 JSON 垃圾桶”。
- 所有参数都要可解释。
- 所有 patch 必须可比较、可审计、可回滚。

交付物至少包括：
- profile schema / sample profiles
- boundary rules
- patch compare utility
- `docs/profiles/instrument_profile_v1.md`
- 对应测试

请直接在仓库内实施。

---

## Thread 06 Prompt — Episode Evaluation 线程

你负责 `episode_evaluation_v1` 的生成与规则评估。目标是把“识别结果到底错在哪”标准化，形成 AI 调参的高质量输入。

先阅读：
- `replay_workbench_master_spec_v2.md`
- `docs/replay_workbench_event_model/` 全部文档
- Thread 04 产出的 event episode / belief state 结构
- Thread 05 产出的 instrument profile 结构

请实现以下内容：

1. 落地 `episode_evaluation_v1` 数据结构与生成器。

2. 实现五个评分维度：
   - `hypothesis_selection_score`
   - `confirmation_timing_score`
   - `invalidation_timing_score`
   - `transition_handling_score`
   - `calibration_score`

3. V1 失败模式枚举与识别：
   - `none`
   - `early_confirmation`
   - `late_confirmation`
   - `late_invalidation`
   - `missed_transition`
   - `false_positive`
   - `false_negative`

4. 支持 3 种评估来源：
   - `rule_review_v1`
   - `human_review_v1`
   - `hybrid_review_v1`

5. 至少先实现 `rule_review_v1`：
   - 基于 event lifecycle / validation / invalidation / time window / replacement event 做规则判定
   - 产出 diagnosis / tuning_hints

6. 输出面向 AI 的结构化 diagnosis：
   - `primary_failure_mode`
   - `supporting_reasons`
   - `missing_confirmation`
   - `invalidating_signals_seen`
   - `candidate_parameters`
   - `suggested_direction`

硬约束：
- 不要把它做成交易盈亏表。
- 不要用 AI 直接生成最终 evaluation 真值。
- V1 先追求“稳定可解释”，不要追求覆盖所有错误类型。
- 与 belief state / episode 的字段保持一致。

交付物至少包括：
- evaluation generator
- rule_review_v1
- `docs/evaluation/episode_evaluation_v1.md`
- 至少 5 个 evaluation 样例
- 对应测试

请直接在仓库内实施。

---

## Thread 07 Prompt — AI Tuning 线程

你负责 AI 调参与协作层。目标不是让 AI 自动控制系统，而是让 AI 能读取结构化 bundle，输出调参建议与 patch candidate，并通过安全门进入离线验证流程。

先阅读：
- `replay_workbench_master_spec_v2.md`
- Thread 05 的 profile/patch 基础设施
- Thread 06 的 episode evaluation 结构
- 仓库中任何已有 review/AI 协作相关代码

请实现以下内容：

1. 构建 `tuning_input_bundle_v1`：
   - instrument profile
   - recent closed episodes
   - corresponding episode evaluations
   - positive/negative summary stats
   - patch history
   - recognizer build metadata
   - degradation statistics（如可用）

2. 构建 `tuning_recommendation_v1`：
   - top failure modes
   - recommendations
   - expected improvement
   - risk
   - confidence
   - patch_candidate_ref

3. 构建 `profile_patch_candidate_v1` 与 `patch_validation_result_v1`：
   - schema validation
   - boundary validation
   - offline replay validation result hook
   - human approval placeholder

4. 构建一个离线 AI adapter 层：
   - 输入 bundle
   - 输出 recommendation
   - 不接入识别关键路径
   - 即使没有真实 LLM 调用，也先实现 contract / stub / local runner

5. 输出文档，明确：
   - AI 能做什么
   - AI 不能做什么
   - 安全门流程
   - 为什么禁止 auto apply

硬约束：
- AI recommendation 不能直接生效。
- 不得修改 ontology。
- 不得覆盖 episode evaluation 真值。
- 所有 recommendation 必须结构化。

交付物至少包括：
- tuning bundle builder
- recommendation contract
- patch candidate pipeline scaffold
- `docs/tuning/ai_tuning_contract_v1.md`
- 样例 bundle / recommendation / patch
- 对应测试

请直接在仓库内实施。

---

## Thread 08 Prompt — Replay Workbench API / UI Projection 线程

你负责 review/workbench 投影层。目标是让 replay workbench 能稳定查看 belief state、episodes、episode evaluations、AI tuning recommendations，并明确展示 degraded / freshness / profile version / engine version。

先阅读：
- `replay_workbench_master_spec_v2.md`
- `README.md`
- 现有 replay workbench / review endpoints / web UI 相关代码
- Thread 04 / 06 / 07 产出的对象结构

请实现以下内容：

1. 构建或增强 review/read APIs：
   - 查询 belief state timeline
   - 查询 event episodes
   - 查询 episode evaluation
   - 查询 tuning recommendations / patch candidates
   - 查询 current profile / engine metadata
   - 查询 health / degraded status

2. 为 replay/workbench 准备 projection 输出：
   - time window 过滤
   - instrument 过滤
   - session/date 过滤
   - timeline friendly JSON

3. 如果仓库已有前端或 workbench 页面，增强显示：
   - 当前 regime 概率
   - top event hypotheses
   - active anchors
   - transition watch
   - data completeness / freshness
   - degraded badges
   - closed episodes 列表
   - episode evaluation 面板
   - AI recommendation / patch compare 面板

4. 至少提供无前端时也可使用的 read API + 示例响应。

硬约束：
- projection 是投影层，不是底层识别逻辑。
- 不要把 UI 绑定成唯一信息源。
- 即使没有 AI recommendation，也必须能正常查看 belief state / episode / evaluation。

交付物至少包括：
- review/read API
- projection builders
- `docs/workbench/replay_workbench_projection_v1.md`
- 如适用，增强现有 workbench 页面
- API tests

请直接在仓库内实施。

---

## Thread 09 Prompt — Golden Cases / Tests / Rebuild / CI 线程

你负责把整个蓝图变成“可验证、可回放、可回归”的工程系统。目标是：没有这条线程，本项目就只是能跑；有了这条线程，项目才算可用。

先阅读：
- `replay_workbench_master_spec_v2.md`
- 所有 samples、tests、scripts、现有 replay 工具
- Thread 01 ~ Thread 08 的输出结构

请实现以下内容：

1. 构建 golden replay cases：
   - 至少 3 个 `momentum_continuation` 样例
   - 至少 3 个 `balance_mean_reversion` 样例
   - 至少 3 个 `absorption_to_reversal_preparation` 样例
   - 至少 3 个失败/降级案例（例如 `degraded_no_depth`, `degraded_no_ai`, `missed_transition`）

2. 实现 rebuild / replay runner：
   - 从 observations 重建 derived layers
   - 可按 instrument/date/session 执行
   - 可输出 summary report

3. 实现 acceptance tests：
   - schema validation tests
   - migration tests
   - ingest API tests
   - recognition unit/integration tests
   - episode evaluation tests
   - tuning contract tests
   - degraded mode tests
   - rebuild consistency tests

4. 构建 CI：
   - lint
   - type checks
   - tests
   - sample validation

5. 输出验收文档：
   - 如何运行全套测试
   - golden case 说明
   - 失败时如何定位

硬约束：
- 不要只写 happy path。
- 一定要覆盖 degraded mode。
- 一定要覆盖 rebuild consistency。
- 一定要验证 AI 不在关键路径上。

交付物至少包括：
- `samples/golden_cases/`
- `scripts/rebuild/`
- `scripts/validate/`
- `tests/` 增强
- CI 配置
- `docs/testing/acceptance_and_regression.md`

请直接在仓库内实施。

---

# 7. 最后的集成 Prompt（给 Thread 00 收口时用）

当其他线程完成后，把下面这段再发给总集成线程。

## Final Integration Prompt

你现在负责把已经完成的多线程成果收口为一个一致、可运行、可测试、可回放、可审计的仓库版本。

你的任务：
1. 逐项比对 `replay_workbench_master_spec_v2.md` 与当前实现。
2. 检查以下是否统一：
   - ontology 枚举
   - schema 命名
   - version 字段
   - profile / engine / schema version 的写法
   - degraded mode 枚举
   - episode evaluation 字段
   - tuning recommendation 字段
3. 修复跨线程冲突：
   - API 读写契约
   - schema 与模型不一致
   - tests 与 samples 不一致
   - rebuild 流程断裂
4. 统一 README / docs 入口，明确：
   - 系统边界
   - 运行步骤
   - 开发顺序
   - 测试方式
   - 调参流程
5. 输出最终差异总结：
   - 已实现内容
   - 未实现内容
   - 风险点
   - 下一阶段建议

不要大重构，不要引入新方向。目标是收口和对齐。

---

# 8. 你真正该怎么开这些线程

推荐实际操作顺序：

1. 先开 **Thread 00**，让它做 repo scan 与实施台账。
2. 再同时开 **Thread 01 / 02 / 03 / 04**。
3. 当 Thread 01 和 Thread 04 有了稳定 contract 后，再开 **Thread 05 / 06 / 07**。
4. 当 Thread 04 / 06 / 07 的对象成型后，再开 **Thread 08**。
5. **Thread 09** 可以在 Wave 1 后半段就提前开工，越早建立 golden cases 越好。
6. 最后让 **Thread 00** 统一收口。

---

# 9. 并行度建议

虽然你可以开很多线程，但建议：

- **总线程数：10**
- **同时并行上限：5**
- **最关键线程优先级：01 > 04 > 06 > 05 > 07 > 08 > 09**

原因：
- 没有 schema，大家会乱写。
- 没有 recognition skeleton，evaluation 和 tuning 都会漂浮。
- 没有 evaluation，AI 调参就是空中楼阁。

---

# 10. 最终结论

这套方案的核心不是“让很多 Codex 一起乱写”，而是：

- 用 **Thread 00** 保证理念不跑偏
- 用 **Thread 01~04** 打稳底座
- 用 **Thread 05~07** 建立“profile → episode evaluation → AI tuning”闭环
- 用 **Thread 08~09** 把它变成可回放、可验证、可展示的系统

只要你按这个拆法推进，Codex 就不容易把项目重新做成：
- 普通指标集合
- 静态模式识别器
- 自动交易系统
- AI 乱改参数的黑盒

而会更接近你真正要的东西：

**高可用的事件识别系统 + 高可用的 AI 诊断/调参协作系统。**
