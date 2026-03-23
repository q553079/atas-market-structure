# ADR-004 Degraded Mode And Data Completeness

- Status: Accepted
- Date: 2026-03-23
- Owner: Integration Thread

## Context

`docs/k_repair/replay_workbench_master_spec_v2.md` 明确要求：

- depth/DOM 缺失时必须降级运行，而不是崩溃
- 关键输出尽量携带 `data_status` / `freshness` / `completeness`
- degraded continuity 是验收项

同时，主规格内部还有一个命名不一致：

- degraded enum 章节使用 `degraded_no_depth`
- 7.3A 的旧描述仍写 `recognition_mode = bar_anchor_only`

仓库需要一个统一、可测试、可回放的最终口径。

## Decision

仓库 canonical degraded naming 统一为：

- `degraded_no_depth`
- `degraded_no_dom`
- `degraded_no_ai`
- `degraded_stale_macro`
- `replay_rebuild_mode`

仓库 canonical recognition mode 统一为：

- `normal`
- `degraded_no_depth`
- `degraded_no_dom`
- `replay_rebuild_mode`

兼容性策略：

- 读取层继续接受旧值 `bar_anchor_only`
- 读取层继续接受旧值 `no_depth` / `no_dom` / `no_ai` / `stale_macro` / `replay_rebuild`
- 输出层、samples、tests、docs 统一写 canonical prefixed names

## Rules

1. depth 不可用时：
   - `degraded_no_depth` 进入 `data_status.degraded_modes`
   - `recognition_mode` 输出 `degraded_no_depth`
   - depth/DOM evidence bucket 标记 unavailable 或降权
2. DOM 不可用时：
   - `degraded_no_dom` 进入 `data_status.degraded_modes`
   - recognition 不因 DOM 缺失而终止
3. AI 不可用时：
   - `degraded_no_ai` 进入 `data_status.degraded_modes`
   - recognition 继续运行
4. 宏观/过程上下文陈旧时：
   - `degraded_stale_macro` 进入 `data_status.degraded_modes`
   - regime posterior 做保守化处理
5. replay rebuild 模式下：
   - `replay_rebuild_mode` 进入 `data_status.degraded_modes`
   - completeness 可下降到 `gapped`

## Consequences

正面结果：

- API、samples、tests、projection、health badge 使用同一套 degraded naming
- 旧样例和旧数据库值仍可被兼容解析
- spec 内部旧字样不会继续扩散到新实现

代价：

- 代码中需要保留少量 alias 兼容逻辑
- 文档必须明确说明 canonical 输出与 legacy alias 的边界

## Acceptance Signal

验收时至少确认：

1. `belief_state_snapshot_v1` 样例输出 canonical degraded naming
2. golden replay case 使用 canonical degraded naming
3. health/data-quality/workbench projection 使用 canonical degraded naming
4. legacy `bar_anchor_only` 和 `no_*` 旧值仍可被解析
