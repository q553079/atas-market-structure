# ADR-001 Observed Vs Derived

- Status: Accepted
- Date: 2026-03-23
- Owner: Integration Thread

## Context

`docs/k_repair/replay_workbench_master_spec_v2.md`、`docs/architecture.md` 与 event model 文档都明确要求：

- observed facts 与 derived interpretation 必须分离
- 底层识别不得把结论直接写回原始观测
- 系统必须保留可回放、可重建、可审计的历史链路

当前仓库已经有：

- `models/_observed.py`
- `models/_derived.py`
- `repository.py` 中的 append-only `ingestions`

但 replay snapshot、analysis、focus region、AI review 等对象在语义上仍有混层风险。

## Decision

项目统一采用以下分层规则：

1. `observed facts`
   - 只保存事实、测量、原始或近原始观测
   - 不携带最终市场结论
   - 允许来源包括 ATAS adapter、market structure snapshot、depth snapshot、history bars、process context
2. `derived interpretation`
   - 只由 deterministic rule engine 或离线评估逻辑生成
   - 必须可从 observed facts 重建
   - 不允许回写覆盖 observed payload
3. projection / UI / AI objects
   - 视为 derived 或 projection 层
   - 不是原始真相层
4. replay snapshot
   - 视为 replay/projection bundle
   - 可以承载 observed 片段与 projection 结果
   - 但不能被视为未来 belief chain 的唯一真相来源

## Rules

1. 新增 observation schema 一律放 observation 层命名空间
2. 新增 belief/episode/evaluation 一律放 derived 层命名空间
3. 不允许把以下字段直接写回 observed 对象：
   - regime
   - event hypothesis
   - belief state
   - episode evaluation
4. observed API 与 recognition API 必须逻辑分离
5. UI 和 AI 只消费 derived/projection 层，不修改 observed facts

## Consequences

正面结果：

- 回放与重建边界清晰
- hindsight bias 更容易控制
- 版本追踪更容易统一
- feature/evaluation/AI plane 可以独立演化

代价：

- 需要维护更多 schema
- 需要在 API 与存储层显式区分 observed 与 derived
- replay snapshot 这种过渡对象必须标注清楚其角色，不得滥用

## Non-Goals

本 ADR 不规定具体 probability update 算法，也不规定 UI 展示形态。它只规定对象分层边界。
