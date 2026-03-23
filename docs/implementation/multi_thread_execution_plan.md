# Multi-Thread Execution Plan

本文档保留“多线程施工计划”这个文件名，但内容已经更新为本轮集成收口时的执行台账，用来回答两件事：

1. 哪些线程目标已经落地
2. 哪些线程成果仍需继续补完

## 1. 总体状态

| 线程 | 目标 | 当前状态 |
|---|---|---|
| Thread 0 | 集成收口 / ADR / README / checklist | 已完成本轮收口 |
| Thread 1 | ontology / profile / schema / samples | 已基本落地 |
| Thread 2 | deterministic recognition core | 已落地 |
| Thread 3 | episode evaluation / tuning core | 已落地 |
| Thread 4 | projection / API / workbench read model | 已落地，补了 spec alias |
| Thread 5 | golden replay / sample validation / rebuild tests | 已落地 |

## 2. 线程成果台账

### Thread 0：总集成线程

职责：

- ADR
- 命名统一
- 版本字段统一
- README / docs 入口统一
- API 契约收口

本轮主要触达：

- `README.md`
- `docs/implementation/repo_gap_analysis.md`
- `docs/implementation/multi_thread_execution_plan.md`
- `docs/implementation/integration_acceptance_checklist.md`
- `docs/adr/ADR-004-degraded-mode-and-data-completeness.md`
- `docs/recognition/recognition_pipeline_v1.md`

### Thread 1：Ontology / Profile / Contract

已落地成果：

- `src/atas_market_structure/ontology.py`
- `src/atas_market_structure/profile_services.py`
- `src/atas_market_structure/profile_loader.py`
- `schemas/instrument_profile_v1.schema.json`
- `samples/profiles/*.yaml`

当前判断：

- ontology 已固定
- profile / build / patch candidate 合同已存在
- sample contract 已存在

### Thread 2：Recognition Core

已落地成果：

- `src/atas_market_structure/recognition/*`
- `src/atas_market_structure/models/_enums.py`
- `src/atas_market_structure/models/_replay.py`
- `src/atas_market_structure/storage_models.py`
- `src/atas_market_structure/storage_repository.py`

当前判断：

- feature -> regime -> hypothesis -> belief -> episode 主链已存在
- degraded mode 已可运行
- append-only / versioned state 边界已明确

### Thread 3：Evaluation / Tuning

已落地成果：

- `src/atas_market_structure/evaluation_services.py`
- `src/atas_market_structure/tuning_services.py`
- `samples/episode_evaluations/*`
- `samples/tuning/*`

当前判断：

- rule-first evaluation 已落地
- tuning recommendation / patch candidate / validation result 数据模型已落地
- promotion gate 仍未形成完整运营闭环

### Thread 4：Projection / API / Workbench

已落地成果：

- `src/atas_market_structure/workbench_projection_services.py`
- `src/atas_market_structure/app.py`
- `tests/test_workbench_projection_api.py`

当前判断：

- `/api/v1/workbench/review/*` read-model 已落地
- 本轮已补齐薄 alias：
  - `GET /api/v1/belief/latest`
  - `GET /api/v1/episodes/latest`
  - `POST /api/v1/review/episode-evaluation`
  - `GET /api/v1/review/episode-evaluation/{episode_id}`
  - `GET /health/recognition`

### Thread 5：Golden Replay / Validation

已落地成果：

- `samples/golden_cases/*`
- `src/atas_market_structure/golden_cases.py`
- `src/atas_market_structure/rebuild_runner.py`
- `tests/test_golden_replay_cases.py`
- `tests/test_rebuild_runner.py`
- `tests/test_sample_validation.py`

当前判断：

- golden replay / rebuild / sample validation 已建立
- deterministic replay compare 还未扩展到 tuning patch promotion gate

## 3. 当前高冲突文件

这些文件已经被收口线程统一处理，后续修改仍需谨慎：

- `src/atas_market_structure/app.py`
- `src/atas_market_structure/models/_enums.py`
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/workbench_projection_services.py`
- `README.md`

## 4. 当前仍未完成的执行项

这些项目仍是 backlog，不建议再以“平行 feature thread”方式发散：

1. `POST /api/v1/rebuild/belief`
2. `POST /api/v1/tuning/recommendation`
3. `POST /api/v1/tuning/patch/validate`
4. `POST /api/v1/tuning/patch/promote`
5. offline replay compare runner
6. patch promotion 审批与落地流程

## 5. 下一轮建议触达文件

若继续收口 backlog，建议按以下顺序推进：

1. `src/atas_market_structure/app.py`
2. `src/atas_market_structure/tuning_services.py`
3. `src/atas_market_structure/profile_services.py`
4. `src/atas_market_structure/rebuild_runner.py`
5. `tests/test_workbench_projection_api.py`
6. `tests/test_tuning_services.py`
7. `tests/test_rebuild_runner.py`

## 6. 本轮执行结论

本仓库已经从“模块缺失期”进入“接口与命名收口期”。后续工作的优先级应该是：

1. 完成剩余 spec HTTP 合同
2. 完成 tuning 的 replay validate / promote 流程
3. 继续清理旧 fixture 与旧别名
