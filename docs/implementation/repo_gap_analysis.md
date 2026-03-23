# Repo Gap Analysis

## 1. 文档定位

本文档是本轮总集成线程的 repo scan 结果。它只做三件事：

1. 说明当前仓库已经有什么
2. 说明这些实现与 `docs/k_repair/replay_workbench_master_spec_v2.md` 之间的接缝与缺口
3. 给后续 feature 线程提供不可越界的集成边界

如果本文件与其他旧文档冲突，以 `docs/k_repair/replay_workbench_master_spec_v2.md` 为准。

## 2. 本次扫描输入

本次扫描已完整覆盖以下资料：

- `docs/k_repair/replay_workbench_master_spec_v2.md`
- `README.md`
- `docs/architecture.md`
- `docs/replay_workbench_event_model/replay_workbench_event_reasoning_playbook.md`
- `docs/replay_workbench_event_model/replay_workbench_event_trading_training_checklist.md`
- `docs/replay_workbench_event_model/replay_workbench_hidden_state_event_memory_model.md`
- `docs/replay_workbench_event_model/replay_workbench_tradable_event_templates.md`
- 当前 `src/`, `schemas/`, `scripts/`, `tests/` 目录结构

## 3. 现有代码结构盘点

### 3.1 `src/atas_market_structure/` 现状

当前代码主体已经具备以下模块簇：

| 模块簇 | 现有文件 | 现状判断 |
|---|---|---|
| HTTP 应用与路由 | `app.py`, `server.py`, `app_routes/*` | 已有统一入口，可承接新 API |
| 领域模型 | `models/*`, `models.py` | 已有 observed / derived / replay / chat 契约，但未覆盖 Master Spec v2 的 belief/episode/evaluation/profile |
| 观测与桥接 | `services.py`, `adapter_services.py`, `adapter_bridge/*`, `depth_services.py` | 已有 ingest 与 observed->derived skeleton，适合复用 |
| Replay Workbench | `workbench_services.py`, `static/*` | 已有 replay snapshot、cache、backfill、AI review/chat UI，但不是 spec v2 的 recognition/belief 主链 |
| 分析编排 | `analysis_orchestration_services.py`, `position_health_services.py`, `regime_monitor_services.py`, `strategy_selection_engine.py` | 有轻量分析与 replay 辅助逻辑，但 ontology 与 spec v2 不一致 |
| 存储 | `repository.py`, `repository_clickhouse.py`, `chart_candle_service.py` | 已有 append-only `ingestions` 主入口和 chart candle 能力，可作为新 derived log 的承载层 |
| Realtime / Infra | `realtime_*`, `ingestion_backfill.py`, `chart_candle_backfill.py` | 偏基础设施，可复用但不是本轮主实现焦点 |

### 3.2 `schemas/` 现状

现有 schema 主要覆盖：

- `market_structure`
- `event_snapshot`
- `depth_snapshot`
- adapter continuous / trigger burst / history bars / history footprint
- replay workbench snapshot / build / live / AI chat / AI review / operator entry

缺失的 spec v2 contract：

- `instrument_profile_v1`
- `belief_state_snapshot`
- `event_episode`
- `episode_evaluation_v1`
- `tuning_recommendation`
- `profile_patch_candidate`

### 3.3 `scripts/` 现状

现有脚本集中在：

- ClickHouse / DolphinDB / backfill / migration / service launcher

缺失的 spec v2 脚本：

- belief rebuild runner
- profile / schema validation helper
- golden replay rebuild verifier
- offline patch validator

### 3.4 `tests/` 现状

现有测试已覆盖：

- API 基础路由
- replay builder
- adapter bridge
- chart candle backfill
- repo hybrid / raw mirror
- timezone capture
- UI Playwright smoke/regression

缺失的 spec v2 测试层：

- fixed ontology unit tests
- profile registry contract tests
- belief/episode/evaluation contract tests
- degraded mode tests
- deterministic rebuild tests
- golden replay tests

## 4. 与 Master Spec v2 的接缝

### 4.1 已具备且可复用的基础

以下能力已经存在，可直接复用，不应另起炉灶：

1. `repository.py` 中的 `save_ingestion` / `list_ingestions`
   - 适合继续承载 append-only observed facts 与 append-only derived logs
2. `workbench_services.py` 中的 replay snapshot build / cache / backfill
   - 适合作为 recognition rebuild 的上游输入与 replay 基础设施
3. `models/_observed.py` 与 `models/_derived.py`
   - 已经建立 observed facts 与 derived interpretation 分层意识
4. `app.py`
   - 已有统一 HTTP dispatch，可继续挂 recognition / review / health API
5. `schemas/` 与 `samples/`
   - 已有 contract artifact 习惯，可直接扩展新的 belief / episode / evaluation / profile artifact
6. `tests/test_app.py`
   - 已有 API 集成测试模式，可直接补充 spec v2 路由回归

### 4.2 已有实现与 Master Spec v2 的主要偏差

| 主题 | 当前仓库现状 | 与 Master Spec v2 的偏差 |
|---|---|---|
| ontology 固定 | `models/_enums.py` 与 `regime_monitor_services.py` 使用当前项目自定义分类 | 未落地 spec v2 固定 regime / event hypothesis / phase / evaluation ontology |
| instrument profile | 未发现 `instrument_profile_v1` loader / registry | 缺少版本化 profile 与边界验证 |
| recognizer build | 未发现 `recognizer_build` 对象 | 缺少 engine version 主对象与输出打标机制 |
| belief chain | replay snapshot 存在，但不是 `feature_slice -> regime/event -> belief_state` append-only 主链 | recognition plane 尚未按 spec 成型 |
| event episode | 未发现 spec v2 `event_episode` schema / store / API | 无事件轨迹闭环 |
| episode evaluation | 未发现 `episode_evaluation_v1` | review plane 仍偏 AI review，而非规则评估闭环 |
| degraded mode | replay/backfill 已有完整性处理，但 recognition 没有 formal degraded mode | 未明确 `degraded_no_depth` / `degraded_no_dom` 及其输出字段 |
| 版本字段 | 许多 payload 仅有 `schema_version`，replay snapshot 未普遍携带 `profile_version` / `engine_version` | 不满足 spec 对关键输出的统一版本要求 |
| AI 角色 | AI review/chat 已存在，位置偏前台工作台协作 | 尚未以 spec v2 方式收束到 tuning/review plane，且缺少 rule-first contracts |

## 5. 与 Master Spec v2 的关键冲突点

这些冲突必须在后续线程落地时优先处理。

### 5.1 旧文档中的事件命名与主规格不完全一致

`docs/replay_workbench_event_model/replay_workbench_tradable_event_templates.md` 中存在以下旧命名：

- `mean_reversion`
- `absorption_to_reversal_prep`
- 扩展到 `breakout_acceptance`
- 扩展到 `failed_breakout_rejection`

Master Spec v2 明确要求 V1 真正闭环只保留：

- `momentum_continuation`
- `balance_mean_reversion`
- `absorption_to_reversal_preparation`

结论：

- 事件模板文档仍可作为训练和理念资产保留
- 工程实现不得直接沿用旧 canonical kind
- 若模板文档与主规格冲突，主规格胜出

### 5.2 当前 `regime_monitor_services.py` 的 regime 不是主规格本体

现有测试表明该模块仍使用：

- `trending_up`
- `trending_down`
- `ranging`
- `volatile`
- `quiet`

这不是 Master Spec v2 固定的 6 类 regime。

结论：

- 该模块可继续作为轻量辅助服务存在
- 但不能被提升为 spec v2 的 regime posterior 真值来源

### 5.3 `models_original.py` 是高风险重复模型面

仓库内存在 `models_original.py`，与现行 `models/` 包并行。

结论：

- 新线程不要继续扩展 `models_original.py`
- 所有新 contract 统一进入 `src/atas_market_structure/models/` 子模块

## 6. 模块存在性台账

### 6.1 已存在模块

| 能力 | 现有承载 |
|---|---|
| observed ingestion | `services.py`, `adapter_services.py`, `depth_services.py` |
| append-only 基础存储 | `repository.py` 中 `ingestions` |
| replay snapshot / cache / backfill | `workbench_services.py` |
| AI review/chat plane | `ai_review_services.py`, replay workbench UI |
| chart candle / local history | `chart_candle_service.py`, `chart_candle_backfill.py` |
| strategy / operator workflow | `strategy_selection_engine.py`, operator entry/manual region APIs |

### 6.2 缺失模块

| 能力 | 当前状态 |
|---|---|
| `ontology.py` | 缺失 |
| `profile_registry.py` | 缺失 |
| `schema_registry.py` | 缺失 |
| `recognition/feature_builder.py` | 缺失 |
| `recognition/regime_updater.py` | 缺失 |
| `recognition/event_updater.py` | 缺失 |
| `recognition/anchor_manager.py` | 缺失 |
| `recognition/belief_emitter.py` | 缺失 |
| `recognition/episode_closer.py` | 缺失 |
| `recognition/degraded_mode.py` | 缺失 |
| `review/episode_evaluator.py` | 缺失 |
| `review/rule_review.py` | 缺失 |
| `rebuild/rebuild_runner.py` | 缺失 |
| spec v2 schemas/samples | 缺失 |
| golden replay tests | 缺失 |

### 6.3 建议新增目录

遵循“增量接入、避免大重构”原则，建议新增以下目录，而不是重排整仓：

- `docs/implementation/`
- `docs/adr/`
- `src/atas_market_structure/recognition/`
- `src/atas_market_structure/review/`
- `src/atas_market_structure/rebuild/`
- `schemas/profile/`
- `schemas/belief/`
- `schemas/episode/`
- `schemas/evaluation/`
- `samples/golden_replays/`
- `samples/episode_evaluations/`
- `tests/unit/`
- `tests/contract/`
- `tests/integration/`
- `tests/golden/`

注意：

- schema/sample/test 目录可以先增量创建，不要求一轮内整体迁移旧文件
- 旧平铺文件允许继续保留，直到总集成阶段再统一

## 7. 集成层面的高风险触点

以下文件是后续线程最容易撞车的位置，应尽量串行或由集成线程最终收口：

- `src/atas_market_structure/app.py`
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/models/__init__.py`
- `schemas/*`
- `samples/*`
- `tests/test_app.py`

建议：

1. 新 contract 与新 service 尽量先放新文件
2. 只在最后一层再改 `app.py` / `models/__init__.py` 做导出与路由接线
3. Replay UI 相关文件不要被 ontology/profile 线程直接改动

## 8. 本轮集成结论

当前仓库已经具备：

- 本地 ingest 与 replay infrastructure
- observed / derived 分层意识
- workbench UI 与 AI 协作外壳
- append-only ingestion 存储习惯

但距离 Master Spec v2 仍缺少四个关键中枢：

1. 固定 ontology 与 versioned profile/build
2. deterministic recognition 主链
3. episode / evaluation 闭环
4. degraded mode + 统一版本字段 + contract artifacts

因此后续 feature 线程应严格围绕这四个中枢推进，而不是继续扩散新的 UI 特性或新的事件命名。
