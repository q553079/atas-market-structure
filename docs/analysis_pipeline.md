# Analysis Pipeline — 入口、数据流、配置、限制

## 架构概览

```
策略库 (strategy_index.json)
    ↓
StrategySelectionEngine ← event_kinds + reason_codes
    ↓
┌─────────────────────────────────────────────────┐
│  三层分析编排 (analysis_orchestration_services)  │
│                                                  │
│  Tier 1: LightweightMonitorService (无LLM)       │
│    → regime + health + suppressor + 是否触发深分析│
│                                                  │
│  Tier 2: FullMarketAnalysisService (人工触发)     │
│    → 全行情分析 + 策略候选 + 风险提示 + briefing  │
│                                                  │
│  Tier 3: DeepRegionAnalysisService (区域深分析)   │
│    → 事件链 + 证据 + verdict + 持仓影响          │
└─────────────────────────────────────────────────┘
    ↓
FocusRegionReviewService (结构化沉淀)
    ↓ 反哺
策略候选 / AI briefing / 持仓健康度 / 复盘案例库
```

## 新增模块清单

| 文件 | 职责 | 消费者 |
|------|------|--------|
| `strategy_selection_engine.py` | 数据驱动策略选择，event_kind/reason_code → strategy_id 映射 | workbench_services, 三层分析 |
| `position_health_services.py` | 持仓健康度评估 (health_score/state/warnings/coaching) | 三层分析, AI briefing |
| `regime_monitor_services.py` | 轻量周期监控 (regime/bias/volatility，无LLM) | Tier 1 monitor, Tier 2 分析 |
| `analysis_orchestration_services.py` | 三层分析编排 | app.py 新端点 |
| `focus_region_review_services.py` | 结构化沉淀 + 截图/框选输入 | app.py 新端点, 复盘 |

## 入口

### Tier 1: 轻量周期监控
- Python: `LightweightMonitorService.run(snapshot, entries)`
- HTTP: `POST /api/v1/analysis/lightweight-monitor`
  - Body: `{"cache_key": "...", "previous_focus_region_count": 0}` 或 `{"snapshot": {...}}`
- 成本: 零 LLM，纯本地逻辑
- 频率: 建议每 2-5 分钟
- 输出: `LightweightMonitorResult` (regime, health, suppressor, 是否建议触发深分析)

### Tier 2: 全行情分析
- Python: `FullMarketAnalysisService.analyze(snapshot, entries)`
- HTTP: `POST /api/v1/analysis/full-market`
  - Body: `{"cache_key": "...", "replay_ingestion_id": "..."}` 或 `{"snapshot": {...}}`
- 成本: 中等（可选 LLM 增强）
- 触发: 人工点击"全行情分析"按钮
- 输出: `FullMarketAnalysisResult` (environment_summary, actionable_summary, risk_alerts, strategy_candidates)

### Tier 3: 区域深分析
- Python: `DeepRegionAnalysisService.analyze_region(snapshot, region, entries)`
- HTTP: `POST /api/v1/analysis/deep-region`
  - Body: `{"cache_key": "...", "region": {...}, "source_type": "manual_marked"}`
- 成本: 聚焦高价值区域
- 触发: 人工标注区域 / AI 建议区域 / web 框选 / ATAS 截图
- 输出: `DeepRegionAnalysisResult` (event_chain, verdict, evidence, no_trade_flags)

### 结构化沉淀
- 存储: `POST /api/v1/analysis/store-review` — 深分析 + 自动存储 review
- 确认: `POST /api/v1/analysis/confirm-review` — `{"review_id": "..."}`
- 拒绝: `POST /api/v1/analysis/reject-review` — `{"review_id": "..."}`
- 列表: `GET /api/v1/analysis/reviews?instrument_symbol=NQ&status=confirmed`
- 反哺: `GET /api/v1/analysis/review-feedback?instrument_symbol=NQ` → 注入 AI briefing

### 截图/框选输入
- HTTP: `POST /api/v1/analysis/screenshot-input`
  - Body: `{"source_type": "atas_screenshot", "instrument_symbol": "NQ", "image_url": "...", ...}`
- 支持: `atas_screenshot` / `web_box_select` 两种 source_type

### 所有分析端点的 snapshot 解析
- 方式一: 传 `cache_key` — 从已有 replay cache 中加载 snapshot
- 方式二: 传 `snapshot` — 直接内联 snapshot JSON
- 方式三: 传 `replay_ingestion_id` — 自动加载对应的 operator entries

## Token 成本控制

| 层级 | 成本 | 频率 | 说明 |
|------|------|------|------|
| Tier 1 轻量监控 | 零 | 每 2-5 分钟 | 纯本地，无 LLM |
| Tier 2 全行情 | 中 | 人工触发 | 可选 LLM 增强 |
| Tier 3 区域深分析 | 高 | 人工触发 | 聚焦单区域 |
| 沉淀/反哺 | 零 | 随分析 | 纯存储查询 |

## 约束

- 不修改 models.py 现有契约
- 不修改 ATAS 采集器
- 不修改 replay/workbench 路由
- 新增字段通过独立模块提供，不破坏旧接口
- 沉淀数据使用现有 AnalysisRepository 的 ingestion 表，kind='focus_region_review'

## 反哺机制

confirmed 的 review 记录通过 `get_feedback_for_briefing()` 返回紧凑格式：
- 历史 verdict 作为 AI 先验
- 匹配的 strategy_id 提升候选权重
- 历史 no-trade flag 强化抑制条件
- 历史 evidence 作为参考基线
