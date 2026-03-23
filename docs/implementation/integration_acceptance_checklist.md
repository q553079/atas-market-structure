# Integration Acceptance Checklist

本清单用于其他线程完成后，由总集成线程统一验收。

## A. 主规格对齐

- [ ] 任何实现若与 `docs/k_repair/replay_workbench_master_spec_v2.md` 冲突，已明确按主规格修正
- [ ] 未新增自定义 ontology
- [ ] V1 真正闭环事件仍只包含：
- [ ] `momentum_continuation`
- [ ] `balance_mean_reversion`
- [ ] `absorption_to_reversal_preparation`

## B. 分层边界

- [ ] observed facts 与 derived interpretation 使用独立对象和独立 schema
- [ ] 未把 regime / event / evaluation 结果直接回写到 observed payload
- [ ] replay/projection 对象未被当作唯一原始真相层

## C. Append-Only 与 Versioning

- [ ] observations append-only
- [ ] feature slices append-only
- [ ] posteriors append-only
- [ ] belief states append-only
- [ ] episodes append-only
- [ ] episode evaluations append-only
- [ ] instrument profile 有稳定版本号
- [ ] recognizer build 有稳定版本号
- [ ] memory anchor 的可变状态采用版本化或快照化写法

## D. 固定字段与命名

- [ ] `schema_version` 已出现在所有关键输出
- [ ] `profile_version` 已出现在所有关键输出
- [ ] `engine_version` 已出现在所有关键输出
- [ ] 输出尽可能携带 `data_status`
- [ ] 输出尽可能携带 `freshness`
- [ ] 输出尽可能携带 `completeness`
- [ ] 事件 kind 名称与主规格一致
- [ ] regime 名称与主规格一致
- [ ] phase 名称与主规格一致
- [ ] evaluation failure mode 名称与主规格一致

## E. Recognition Plane

- [ ] 已落地固定 ontology constants
- [ ] 已落地 `instrument_profile_v1`
- [ ] 已落地 `recognizer_build`
- [ ] 已存在 deterministic feature builder
- [ ] 已存在 deterministic regime updater
- [ ] 已存在 deterministic event updater
- [ ] 已存在 anchor manager
- [ ] 已存在 belief emitter
- [ ] 已存在 event episode closer
- [ ] 识别链路在没有 AI 的情况下完整可运行

## F. Degraded Mode

- [ ] depth 缺失时 recognition 不报错终止
- [ ] DOM 缺失时 recognition 不报错终止
- [ ] 最少支持 `normal`
- [ ] 最少支持 `degraded_no_depth`
- [ ] 最少支持 `degraded_no_dom`
- [ ] 降级状态有显式字段输出
- [ ] 降级状态下 confidence / completeness 会反映缺失，而不是伪装成完整数据

## G. Review / Evaluation Plane

- [ ] 已落地 `event_episode` contract
- [ ] 已落地 `episode_evaluation_v1` contract
- [ ] 每个闭合 episode 都能生成 evaluation
- [ ] evaluation 来源不是纯 AI
- [ ] 至少支持失败模式：
- [ ] `none`
- [ ] `early_confirmation`
- [ ] `late_confirmation`
- [ ] `late_invalidation`
- [ ] `missed_transition`
- [ ] `false_positive`
- [ ] `false_negative`

## H. API 验收

- [ ] 已提供 `GET /api/v1/belief/latest`
- [ ] 已提供 `GET /api/v1/episodes/latest`
- [ ] 已提供 `POST /api/v1/rebuild/belief`
- [ ] 已提供 `POST /api/v1/review/episode-evaluation`
- [ ] 已提供 `GET /api/v1/review/episode-evaluation/{episode_id}`
- [ ] 已提供 `/health/recognition`
- [ ] 已提供 `/health/data-quality`

## I. Contract Artifacts

- [ ] `schemas/` 已补齐 profile / belief / episode / evaluation contracts
- [ ] `samples/` 已补齐对应 sample payload
- [ ] 样例中的版本字段完整
- [ ] 样例中的 degraded mode 场景可验证

## J. Tests

- [ ] 新增 unit tests
- [ ] 新增 contract tests
- [ ] 新增 integration tests
- [ ] 新增 golden replay tests
- [ ] 覆盖 deterministic rebuild
- [ ] 覆盖 degraded continuity
- [ ] 覆盖三类 V1 tradable event 的闭环

## K. 文档与命名收口

- [ ] README 已同步到当前实现状态
- [ ] `docs/implementation/repo_gap_analysis.md` 已根据最终落地情况回填
- [ ] `docs/implementation/multi_thread_execution_plan.md` 已更新为最终执行结果
- [ ] 旧文档中的冲突命名已标明“Master Spec v2 优先”
- [ ] 新增目录没有破坏现有仓库结构

## L. 最终集成动作

在准备合并前，总集成线程还需逐项确认：

- [ ] `app.py` 路由接线无冲突
- [ ] `models/__init__.py` 导出无重复和无旧别名污染
- [ ] `workbench_services.py` 没有把 AI 引入关键路径
- [ ] 高冲突文件的最终命名与导入关系稳定
- [ ] 最终 diff 中不存在“顺手改 unrelated logic”的噪音
