# ADR-003 AI Not On Critical Path

- Status: Accepted
- Date: 2026-03-23
- Owner: Integration Thread

## Context

仓库当前已经有：

- replay AI review
- replay AI chat
- strategy-library assisted AI workflows

这些能力有价值，但 Master Spec v2 明确要求：

- AI 不得进入 recognition 关键路径
- AI 不得在线热更新参数
- AI 不得替代底层状态机

## Decision

项目统一采用以下职责边界：

### 规则/特征引擎负责

- feature 计算
- regime/event posterior 更新
- memory anchor interaction
- belief state 产出
- event episode 闭合
- episode evaluation 的 rule-first 结果

### AI 负责

- 解释 belief state
- 总结 supporting evidence / missing confirmation
- 输出复盘叙事
- 产出 tuning recommendation / patch candidate
- 辅助人类 review 与协作

一句话：

`机器算状态，AI 讲故事。`

## Rules

1. recognition API 在没有 AI 的情况下必须完整可用
2. episode evaluation 的最终判定来源不能是纯 AI
3. tuning recommendation 只能是建议，不得自动生效
4. profile patch 必须经过离线验证与人工/规则门控
5. AI 不可用时：
   - 核心识别继续运行
   - 服务状态降级但不中断

## Consequences

正面结果：

- recognition 可测试、可重放、可审计
- AI 宕机不会拖垮核心链路
- 过拟合与黑箱风险可控

代价：

- 需要同时维护 deterministic layer 与 AI explanation layer
- AI 不能直接“兜底”底层建模缺口

## Non-Goals

本 ADR 不禁止 AI 参与开发、离线分析或 patch generation。它只禁止 AI 成为线上核心状态产出的单点依赖。
