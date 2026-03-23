# ADR-002 Append-Only And Versioned State

- Status: Accepted
- Date: 2026-03-23
- Owner: Integration Thread

## Context

Master Spec v2 明确规定：

- observations、feature slices、posteriors、belief states、episodes、episode evaluations 必须 append-only
- instrument profile、recognizer build、memory anchor freshness 等可变对象必须版本化

当前仓库已有 append-only 倾向：

- `repository.py` 的 `ingestions` 适合保存 append-only records

但当前仓库也存在少量“更新现有记录”的路径，例如 replay cache invalidation 会更新已有 replay payload。

## Decision

项目统一采用“两类状态边界”：

### A. Append-only event log objects

以下对象永远只追加，不原地覆盖：

- `observation_*`
- `feature_slice`
- `regime_posterior`
- `event_hypothesis_state`
- `belief_state_snapshot`
- `event_episode`
- `episode_evaluation`
- `tuning_recommendation`
- `profile_patch_candidate`

### B. Versioned state objects

以下对象允许“新版本替代旧版本作为当前默认值”，但旧版本必须保留：

- `instrument_profile`
- `recognizer_build`
- `memory_anchor` 的版本化状态视图
- 其他明确声明为 registry/state 的对象

## Rules

1. append-only 对象禁止 update-in-place
2. versioned state 对象必须有稳定版本标识
3. 关键输出统一带：
   - `schema_version`
   - `profile_version`
   - `engine_version`
4. `memory_anchor` 若需要更新 freshness、role profile、state：
   - 优先采用新版本或快照写法
   - 不把旧状态直接抹掉
5. 任何 patch/promote/rollback 都必须留下记录

## Storage Guidance

现阶段优先复用 `repository.py` 的 `save_ingestion` 作为 append-only log 入口。

推荐做法：

- append-only derived objects 先以新 ingestion kind 保存
- versioned registry 对象可以落文件 registry 或专表
- 若未来拆专表，也必须保持可重建和可追溯

## Consequences

正面结果：

- 历史演化链完整
- rebuild compare 成本低
- 调参和回滚有审计链

代价：

- 查询“latest state”需要聚合或 snapshot
- 数据量会上升

## Clarification

现有 replay cache invalidation 属于现存基础设施行为，不应被扩散到 spec v2 的 recognition/evaluation 主链。后续新实现不得以此为 precedent 继续新增 mutable derived objects。
