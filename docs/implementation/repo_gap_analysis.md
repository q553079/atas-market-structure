# Repo Gap Analysis

本文档是 2026-03-23 集成收口后的仓库状态快照。若与其他旧文档冲突，以 `docs/k_repair/replay_workbench_master_spec_v2.md` 为准。

## 1. 结论先行

当前仓库已经不再处于“recognition/evaluation/tuning 模块大面积缺失”的阶段。主要主链已经落地，当前收口重点变成：

1. 命名统一
2. 版本字段统一
3. API 契约补薄兼容层
4. README / docs / samples / tests 对齐
5. 标记仍未闭环的 spec backlog

## 2. 与 Master Spec v2 的已对齐部分

### 2.1 固定 ontology

已落地：

- `src/atas_market_structure/ontology.py`
- `src/atas_market_structure/models/_enums.py`

当前固定 ontology 与主规格一致：

- regime
- event hypothesis
- phase
- evaluation failure mode

### 2.2 观测层与派生层分离

已落地：

- observed 模型：`src/atas_market_structure/models/_observed.py`
- derived / replay / response 模型：`src/atas_market_structure/models/_derived.py`, `src/atas_market_structure/models/_replay.py`, `src/atas_market_structure/models/_responses.py`
- ADR：`docs/adr/ADR-001-observed-vs-derived.md`

当前判断：

- observed facts 与 derived interpretation 已有清晰分层
- replay/workbench projection 已被视为 projection layer，而不是原始真相层

### 2.3 Append-only 与 versioned state

已落地：

- append-only belief / episode / evaluation / tuning recommendation 存储接口
- versioned profile / recognizer build / memory anchor state
- ADR：`docs/adr/ADR-002-append-only-and-versioned-state.md`

### 2.4 AI 非关键路径

已落地：

- deterministic recognition 不依赖 AI
- evaluation 是 rule-first
- tuning recommendation 输出 `allow_ai_auto_apply = false`
- ADR：`docs/adr/ADR-003-ai-not-on-critical-path.md`

### 2.5 degraded mode

已落地：

- recognition 在 depth/DOM 缺失下继续运行
- `data_status` / `freshness` / `completeness` 已进入关键输出
- canonical degraded naming 已统一为 prefixed names

## 3. 当前已存在模块台账

### 3.1 主链模块

| 能力 | 现有文件 | 当前状态 |
|---|---|---|
| Ontology | `src/atas_market_structure/ontology.py` | 已落地 |
| Instrument profile | `src/atas_market_structure/profile_services.py`, `src/atas_market_structure/profile_loader.py` | 已落地 |
| Recognizer build | `src/atas_market_structure/recognition/defaults.py`, `profile_services.py` | 已落地 |
| Recognition pipeline | `src/atas_market_structure/recognition/*` | 已落地 |
| Episode evaluation | `src/atas_market_structure/evaluation_services.py` | 已落地 |
| Tuning recommendation | `src/atas_market_structure/tuning_services.py` | 已落地 |
| Rebuild runner | `src/atas_market_structure/rebuild_runner.py` | 已落地 |
| Projection/read model | `src/atas_market_structure/workbench_projection_services.py` | 已落地 |

### 3.2 合同资产

| 能力 | 现有路径 | 当前状态 |
|---|---|---|
| Profiles | `samples/profiles/*.yaml`, `schemas/instrument_profile_v1.schema.json` | 已落地 |
| Recognition samples | `samples/recognition/*.sample.json` | 已落地 |
| Episode evaluation samples | `samples/episode_evaluations/*.sample.json` | 已落地 |
| Tuning samples | `samples/tuning/*.json` | 已落地 |
| Golden replay cases | `samples/golden_cases/*.case_set.json` | 已落地 |

### 3.3 测试资产

| 能力 | 现有文件 | 当前状态 |
|---|---|---|
| Recognition | `tests/test_recognition_pipeline.py` | 已落地 |
| Evaluation | `tests/test_episode_evaluation.py` | 已落地 |
| Tuning | `tests/test_tuning_services.py` | 已落地 |
| Rebuild | `tests/test_rebuild_runner.py` | 已落地 |
| Sample validation | `tests/test_sample_validation.py` | 已落地 |
| Golden replay | `tests/test_golden_replay_cases.py` | 已落地 |
| Projection API | `tests/test_workbench_projection_api.py` | 已落地 |

## 4. 仍需明确标记的 spec backlog

下列能力并非不存在代码基座，而是尚未以“稳定 HTTP 合同 + 完整运营闭环”形式暴露：

| 主题 | 当前状态 | 结论 |
|---|---|---|
| `POST /api/v1/rebuild/belief` | `rebuild_runner.py` 已存在，但未暴露稳定 HTTP 路由 | backlog |
| `POST /api/v1/tuning/recommendation` | `TuningAdvisorService` 已存在，但未暴露稳定 HTTP 路由 | backlog |
| `POST /api/v1/tuning/patch/validate` | `InstrumentProfileService.validate_patch` 已存在，但未暴露稳定 HTTP 路由 | backlog |
| `POST /api/v1/tuning/patch/promote` | promotion 流程未落地 | backlog |
| offline replay compare | 当前为 stub/placeholder | backlog |

## 5. 本次收口解决的跨线程冲突

### 5.1 degraded mode 命名冲突

已统一：

- `degraded_no_depth`
- `degraded_no_dom`
- `degraded_no_ai`
- `degraded_stale_macro`
- `replay_rebuild_mode`

保留兼容：

- `bar_anchor_only`
- `no_depth`
- `no_dom`
- `no_ai`
- `stale_macro`
- `replay_rebuild`

### 5.2 spec API 与当前 workbench API 的落差

当前仓库采取“双层接口”：

- richer read-model API 保留在 `/api/v1/workbench/review/*`
- 薄兼容 alias 暴露：
  - `GET /api/v1/belief/latest`
  - `GET /api/v1/episodes/latest`
  - `POST /api/v1/review/episode-evaluation`
  - `GET /api/v1/review/episode-evaluation/{episode_id}`
  - `GET /health/recognition`

### 5.3 version/schema 命名漂移

已统一到 explicit names：

- `instrument_profile_v1`
- `recognizer_build_v1`
- `belief_state_snapshot_v1`
- `event_episode_v1`
- `episode_evaluation_v1`
- `tuning_recommendation_v1`

## 6. 仍需关注的风险

1. Master Spec v2 自身对 `recognition_mode` 存在 `bar_anchor_only` vs `degraded_no_depth` 的旧新混用。
2. 部分历史测试 fixture 仍保留 `1.0.0` 这类泛 schema 字样，虽然不影响运行，但后续仍值得继续压缩。
3. tuning HTTP 合同未完全暴露，外部调用仍应以当前 service / projection 形态为准。
4. replay cache / replay snapshot 仍是基础设施层，不应被误当作 recognition 原始真相层。

## 7. 当前总判断

仓库当前状态是：

- recognition/evaluation/tuning 主链已存在
- replay/projection/read-model 已存在
- 主要问题不再是“缺模块”，而是“收口与对齐”

因此后续工作不应再发散新方向，而应围绕：

1. backlog HTTP route 暴露
2. offline replay compare
3. patch promotion gate
4. 进一步清理旧 fixture / 旧命名
