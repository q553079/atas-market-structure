# Integration Acceptance Checklist

本清单用于当前仓库版本的最终验收。已完成项直接标记，remaining backlog 保留为未完成。

## A. 主规格对齐

- [x] 主规格以 `docs/k_repair/replay_workbench_master_spec_v2.md` 为准
- [x] 未新增自定义 ontology
- [x] V1 闭环事件只保留：
- [x] `momentum_continuation`
- [x] `balance_mean_reversion`
- [x] `absorption_to_reversal_preparation`

## B. 分层边界

- [x] observed facts 与 derived interpretation 使用独立对象和独立 schema
- [x] 未把 regime / event / evaluation 结果直接回写 observed payload
- [x] replay/projection 对象未被当作唯一原始真相层

## C. Append-Only 与 Versioning

- [x] observations append-only
- [x] feature slices append-only
- [x] posteriors append-only
- [x] belief states append-only
- [x] episodes append-only
- [x] episode evaluations append-only
- [x] tuning recommendations append-only
- [x] instrument profile 有稳定版本号
- [x] recognizer build 有稳定版本号
- [x] memory anchor 的可变状态采用 versioned/snapshot 写法

## D. 固定字段与命名

- [x] `schema_version` 已进入关键输出
- [x] `profile_version` 已进入关键输出
- [x] `engine_version` 已进入关键输出
- [x] 关键输出尽量携带 `data_status`
- [x] 关键输出尽量携带 `freshness`
- [x] 关键输出尽量携带 `completeness`
- [x] event kind 名称与主规格一致
- [x] regime 名称与主规格一致
- [x] phase 名称与主规格一致
- [x] evaluation failure mode 名称与主规格一致
- [x] degraded mode canonical naming 统一为 prefixed names
- [x] legacy `bar_anchor_only` / `no_*` 只作为兼容输入，不再作为 canonical 输出

## E. Recognition Plane

- [x] 已落地固定 ontology constants
- [x] 已落地 `instrument_profile_v1`
- [x] 已落地 `recognizer_build_v1`
- [x] 已存在 deterministic feature builder
- [x] 已存在 deterministic regime updater
- [x] 已存在 deterministic event updater
- [x] 已存在 anchor manager
- [x] 已存在 belief emitter
- [x] 已存在 event episode closer
- [x] 识别链路在没有 AI 的情况下完整可运行

## F. Degraded Mode

- [x] depth 缺失时 recognition 不报错终止
- [x] DOM 缺失时 recognition 不报错终止
- [x] 支持 `normal`
- [x] 支持 `degraded_no_depth`
- [x] 支持 `degraded_no_dom`
- [x] 支持 `degraded_no_ai`
- [x] 支持 `degraded_stale_macro`
- [x] 支持 `replay_rebuild_mode`
- [x] 降级状态有显式字段输出
- [x] 降级状态下 confidence / completeness 会反映缺失，而不是伪装成完整数据

## G. Review / Evaluation Plane

- [x] 已落地 `event_episode` contract
- [x] 已落地 `episode_evaluation_v1` contract
- [x] 闭合 episode 可生成 evaluation
- [x] evaluation 来源不是纯 AI
- [x] failure mode 至少支持：
- [x] `none`
- [x] `early_confirmation`
- [x] `late_confirmation`
- [x] `late_invalidation`
- [x] `missed_transition`
- [x] `false_positive`
- [x] `false_negative`

## H. API 验收

### 已实现的 spec / alias routes

- [x] `GET /api/v1/belief/latest`
- [x] `GET /api/v1/episodes/latest`
- [x] `POST /api/v1/review/episode-evaluation`
- [x] `GET /api/v1/review/episode-evaluation/{episode_id}`
- [x] `GET /health/recognition`
- [x] `GET /health/data-quality`

### 已实现的 richer workbench/read-model routes

- [x] `GET /api/v1/workbench/review/projection`
- [x] `GET /api/v1/workbench/review/belief-state-timeline`
- [x] `GET /api/v1/workbench/review/event-episodes`
- [x] `GET /api/v1/workbench/review/episode-evaluations`
- [x] `GET /api/v1/workbench/review/tuning-recommendations`
- [x] `GET /api/v1/workbench/review/profile-engine`
- [x] `GET /api/v1/workbench/review/health-status`

### 仍属于 backlog 的 spec routes

- [ ] `POST /api/v1/rebuild/belief`
- [ ] `POST /api/v1/tuning/recommendation`
- [ ] `POST /api/v1/tuning/patch/validate`
- [ ] `POST /api/v1/tuning/patch/promote`

## I. Contract Artifacts

- [x] `schemas/` 已补齐至少 `instrument_profile_v1`
- [x] `samples/` 已补齐 profile / recognition / evaluation / tuning / golden replay payload
- [x] 样例中的版本字段已显式命名
- [x] 样例中的 degraded mode 场景可验证

## J. Tests

- [x] recognition tests 已存在
- [x] evaluation tests 已存在
- [x] tuning tests 已存在
- [x] projection API tests 已存在
- [x] rebuild tests 已存在
- [x] golden replay tests 已存在
- [x] sample validation tests 已存在
- [x] 覆盖 deterministic rebuild
- [x] 覆盖 degraded continuity
- [x] 覆盖三类 V1 tradable event 闭环

## K. 文档与命名收口

- [x] README 已同步到当前实现状态
- [x] `docs/implementation/repo_gap_analysis.md` 已根据最终状态回填
- [x] `docs/implementation/multi_thread_execution_plan.md` 已更新为执行台账
- [x] `docs/recognition/recognition_pipeline_v1.md` 已改为当前 canonical naming
- [x] `docs/adr/ADR-004-degraded-mode-and-data-completeness.md` 已说明 canonical naming 与 legacy alias
- [x] 旧文档中的冲突命名已标注“主规格优先 + 仓库 canonical 输出”

## L. 最终集成动作

- [x] `app.py` 路由接线无冲突
- [x] `workbench_services.py` 不把 AI 引入关键路径
- [x] 命名、版本字段、degraded mode 已统一
- [x] 最终 diff 以收口和对齐为主，没有引入新方向

## M. 剩余 TODO

- [ ] 暴露 `rebuild/belief` HTTP 合同
- [ ] 暴露 tuning recommendation / patch validate / patch promote HTTP 合同
- [ ] 把 offline replay compare 从 stub 提升为真实 compare runner
- [ ] 继续清理测试内部遗留的泛 `1.0.0` schema fixture
