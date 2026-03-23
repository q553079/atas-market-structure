# Multi-Thread Execution Plan

## 1. 目标与边界

本计划用于把后续 feature 线程约束在 Master Spec v2 允许的施工面内。

本轮多线程施工的硬边界：

1. 不改 ontology
2. 不把项目做成自动交易系统
3. 不让 AI 进入 recognition 关键路径
4. observed facts 与 derived interpretation 严格分离
5. observations / feature slices / posteriors / belief states / episodes / episode evaluations 保持 append-only
6. instrument profile / recognizer build / memory anchor freshness 等可变对象必须版本化
7. depth/DOM 缺失时必须降级运行，不得抛错终止
8. 所有关键输出统一带 `schema_version`、`profile_version`、`engine_version`

## 2. 当前已有模块与缺失模块

### 2.1 已有模块

| 类别 | 已有文件 |
|---|---|
| HTTP / App | `src/atas_market_structure/app.py`, `server.py`, `app_routes/*` |
| Models | `src/atas_market_structure/models/*` |
| Repo / Storage | `src/atas_market_structure/repository.py`, `repository_clickhouse.py` |
| Ingestion | `services.py`, `adapter_services.py`, `depth_services.py`, `adapter_bridge/*` |
| Replay | `workbench_services.py`, `chart_candle_service.py`, `static/*` |
| AI 协作 | `ai_review_services.py`, replay AI chat/review routes |
| Tests | `tests/test_app.py` 等现有回归 |

### 2.2 缺失模块

| 类别 | 缺失项 |
|---|---|
| Ontology / Profile | `ontology.py`, `profile_registry.py`, `schema_registry.py` |
| Recognition | `feature_builder`, `regime_updater`, `event_updater`, `anchor_manager`, `belief_emitter`, `episode_closer`, `degraded_mode` |
| Review | `episode_evaluator`, `rule_review`, human override contract |
| Rebuild | `rebuild_runner`, compare/verify helpers |
| Contract Artifacts | belief / episode / evaluation / profile schemas and samples |
| Validation | deterministic rebuild tests, degraded tests, golden replay tests |

## 3. 建议新增目录

建议优先新增，而不是大幅重构旧文件：

```text
docs/
  implementation/
  adr/

src/atas_market_structure/
  ontology.py
  profile_registry.py
  schema_registry.py
  recognition/
  review/
  rebuild/

schemas/
  profile/
  belief/
  episode/
  evaluation/

samples/
  golden_replays/
  episode_evaluations/
  tuning_recommendations/

tests/
  unit/
  contract/
  integration/
  golden/
```

说明：

- 这是“增量增加”，不是要求把旧的平铺结构一次性迁完
- 旧路径继续保留，集成阶段再统一命名与索引

## 4. 线程拆分建议

### Thread 0：总集成线程

职责：

- 维护 ADR、台账、验收清单
- 收口命名、版本字段、目录结构
- 负责最终 README / docs 同步

主文件：

- `docs/implementation/*`
- `docs/adr/*`
- 最后阶段触达 `README.md`

不要做：

- 大面积 feature 实现

### Thread 1：Ontology / Profile / Contract Thread

职责：

- 落地固定 ontology constants
- 定义 `instrument_profile_v1`
- 定义 `recognizer_build`
- 产出 belief/episode/evaluation/profile schemas 与 samples

建议主文件：

- `src/atas_market_structure/ontology.py`
- `src/atas_market_structure/profile_registry.py`
- `src/atas_market_structure/schema_registry.py`
- `src/atas_market_structure/models/` 下新 contract 文件
- `schemas/profile/*`
- `schemas/belief/*`
- `schemas/episode/*`
- `schemas/evaluation/*`
- `samples/*`
- `tests/contract/*`

避免直接改：

- `workbench_services.py`
- replay UI 静态文件

依赖：

- 无，优先开工

### Thread 2：Recognition Core Thread

职责：

- 实现 deterministic recognition 主链
- 生成 `feature_slice`
- 更新 regime posterior / event hypothesis / anchor interaction
- 产出 `belief_state_snapshot`
- 闭合 V1 三类事件 episode
- 实现 degraded mode

建议主文件：

- `src/atas_market_structure/recognition/*`
- `src/atas_market_structure/rebuild/*`
- 少量接线到 `app.py`
- 少量导出到 `models/__init__.py`

避免直接改：

- AI chat/review 逻辑
- Replay UI 大量前端代码

依赖：

- Thread 1 的 ontology/profile/contracts 应先稳定

### Thread 3：Episode Evaluation / Review Thread

职责：

- 落地 `episode_evaluation_v1`
- 实现 rule review engine
- 提供 review APIs
- 保持 AI 只消费 evaluation，不替代 evaluation

建议主文件：

- `src/atas_market_structure/review/*`
- `src/atas_market_structure/app.py`
- `tests/unit/*`
- `tests/integration/*`

避免直接改：

- ontology constants
- replay snapshot builder 主逻辑，除非接线必须

依赖：

- Thread 2 已能生成 episode

### Thread 4：Projection / API / Workbench Thread

职责：

- 将 belief / episodes / evaluations 接入 API
- 视需要把 projection 数据接入 workbench service
- 只做最小 UI/response 扩展，不发散新功能

建议主文件：

- `src/atas_market_structure/app.py`
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/app_routes/*`
- `src/atas_market_structure/static/*`
- `tests/test_app.py`
- `tests/playwright_*`

避免直接改：

- profile registry 内部实现
- rule evaluator 内部实现

依赖：

- Thread 2、Thread 3 完成主要 contract

### Thread 5：Golden Replay / Validation Thread

职责：

- 补充 golden replay payload
- 增加 deterministic rebuild 与 degraded continuity 测试
- 验证版本字段与 schema coverage

建议主文件：

- `samples/golden_replays/*`
- `tests/golden/*`
- `tests/contract/*`
- 可增加 `scripts/` 下验证脚本

依赖：

- Thread 1-4 至少完成第一轮 contract 与 API

## 5. 跨线程接口协调规则

所有线程统一遵守以下字段和命名，不得私自漂移。

### 5.1 固定 ontology

固定 regime：

- `strong_momentum_trend`
- `weak_momentum_trend_narrow`
- `weak_momentum_trend_wide`
- `balance_mean_reversion`
- `compression`
- `transition_exhaustion`

固定 tradable event V1：

- `momentum_continuation`
- `balance_mean_reversion`
- `absorption_to_reversal_preparation`

固定 phase：

- `emerging`
- `building`
- `confirming`
- `weakening`
- `resolved`
- `invalidated`

固定 evaluation failure mode：

- `none`
- `early_confirmation`
- `late_confirmation`
- `late_invalidation`
- `missed_transition`
- `false_positive`
- `false_negative`

### 5.2 强制版本字段

以下输出必须带：

- `schema_version`
- `profile_version`
- `engine_version`

尽可能再带：

- `data_status`
- `freshness`
- `completeness`

### 5.3 建议统一 ingestion kind

建议新 derived log 统一使用以下 ingestion kind：

- `feature_slice_v1`
- `regime_posterior_v1`
- `event_hypothesis_state_v1`
- `belief_state_snapshot_v1`
- `event_episode_v1`
- `episode_evaluation_v1`

如果线程采用不同命名，必须先与总集成线程对齐再提交。

### 5.4 recognition mode

最少保留：

- `normal`
- `degraded_no_depth`
- `degraded_no_dom`

如果需要补充额外 mode，可以加在附属枚举里，但不能替代上述两个 degraded mode。

## 6. 共享高冲突文件

以下文件只允许“最后接线线程”或集成线程集中合并：

- `src/atas_market_structure/app.py`
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/models/__init__.py`
- `README.md`

并行线程应优先：

1. 新建独立模块
2. 在 PR 末尾最小化接线 diff
3. 不在共享文件里顺手做 unrelated cleanup

## 7. 推荐执行顺序

1. Thread 1 固定 ontology/profile/schema/contracts
2. Thread 2 基于固定 contracts 落地 recognition core + degraded mode
3. Thread 3 基于 episode 落地 evaluation/review
4. Thread 4 接 API/workbench projection
5. Thread 5 补 golden replay 与回归测试
6. Thread 0 做最终集成收口、文档同步、命名统一

## 8. 最终集成阶段的收口任务

总集成线程在 feature 线程完成后统一负责：

1. README 与 docs 更新
2. 命名统一
3. 版本字段统一
4. schema/sample 目录清点
5. tests 分类与入口整理
6. 检查旧文档里与 Master Spec v2 冲突的字段名并标注“主规格优先”

在此之前，不建议任何 feature 线程自行改写 README 或全仓文档索引。
