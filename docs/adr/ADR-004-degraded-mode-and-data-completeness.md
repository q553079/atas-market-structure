# ADR-004 Degraded Mode And Data Completeness

- Status: Accepted
- Date: 2026-03-23
- Owner: Integration Thread

## Context

Master Spec v2 多处明确要求：

- depth/DOM 缺失时必须降级运行，而不是报错终止
- 所有关键输出尽可能携带 `data_status` / `freshness` / `completeness`
- degraded continuity 是验收重点

当前仓库已经在 replay/backfill 层有完整性处理，但 recognition 层还没有 formal degraded mode 设计。

## Decision

recognition plane 统一采用“显式降级，不隐式失败”的策略。

### 最低限度 recognition mode

- `normal`
- `degraded_no_depth`
- `degraded_no_dom`

实现方如果需要附加模式，可以增加：

- `degraded_sparse_microstructure`
- `degraded_stale_context`

但不得替代上述基础模式。

## Rules

1. depth 不可用时：
   - depth/DOM 相关 evidence bucket 标记为 unavailable 或降权
   - recognition 继续运行
   - 输出 `recognition_mode=degraded_no_depth` 或更具体 mode
2. DOM 不可用时：
   - DOM checks 不参与硬失败
   - 输出 `recognition_mode=degraded_no_dom`
3. 输出必须显式暴露数据质量字段，例如：
   - `data_freshness_ms`
   - `feature_completeness`
   - `depth_available`
   - `dom_available`
   - `ai_available`
4. 降级时允许：
   - 概率更保守
   - missing confirmation 更多
   - confidence 降低
5. 降级时不允许：
   - 抛异常终止 recognition
   - 因单一 evidence 缺失而停止 rebuild

## Consequences

正面结果：

- 深度数据中断不会拖垮回放与识别
- UI 与 review 可以清楚看到“为什么当前信号更弱”
- 测试能明确覆盖 degraded continuity

代价：

- 每个关键输出都要带更多状态字段
- 规则引擎需要处理 unavailable evidence，而不是默认完整数据

## Acceptance Signal

任何线程完成 recognition 相关改动后，至少要能给出：

1. 正常模式样例
2. `degraded_no_depth` 样例
3. `degraded_no_dom` 样例
4. 对应 contract tests
