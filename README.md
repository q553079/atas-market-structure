# ATAS Market Structure

本仓库当前收口到 `docs/k_repair/replay_workbench_master_spec_v2.md` 的 V1 范围，目标是一个本地可运行、可测试、可回放、可审计的 replay workbench 与 deterministic recognition/evaluation/tuning 基座。

说明：

- `docs/k_repair/` 仍保留主规格与历史修复上下文。
- 当历史文档中的实现文件列表与当前代码不一致时，以本 README、`src/atas_market_structure/README.md`、`src/atas_market_structure/app_routes/README.md`、`src/atas_market_structure/models/README.md` 与实际代码为准。

## 主规格与入口

主规格：

- `docs/k_repair/replay_workbench_master_spec_v2.md`

建议阅读顺序：

1. `docs/k_repair/replay_workbench_master_spec_v2.md`
2. `docs/architecture.md`
3. `docs/recognition/recognition_pipeline_v1.md`
4. `docs/workbench/replay_workbench_projection_v1.md`
5. `docs/implementation/repo_gap_analysis.md`
6. `docs/implementation/integration_acceptance_checklist.md`
7. `docs/adr/ADR-001-observed-vs-derived.md`
8. `docs/adr/ADR-002-append-only-and-versioned-state.md`
9. `docs/adr/ADR-003-ai-not-on-critical-path.md`
10. `docs/adr/ADR-004-degraded-mode-and-data-completeness.md`

## 系统边界

本仓库当前实现的是：

- 本地 ingestion 与 replay workbench 基础设施
- deterministic recognition 主链
- append-only belief / episode / episode evaluation / tuning recommendation 数据面
- versioned instrument profile / recognizer build / memory anchor state
- degraded mode 下持续运行，而不是因 depth/DOM 缺失而中断
- rule-first evaluation 与 offline-only tuning recommendation
- workbench projection/read-model API

本仓库明确不做：

- 自动交易
- AI 在线热更新参数
- AI 进入 recognition 关键路径
- 修改固定 ontology

## 当前已实现范围

### Recognition

- 固定 ontology 已落地在 `src/atas_market_structure/ontology.py`
- V1 闭环事件只保留：
  - `momentum_continuation`
  - `balance_mean_reversion`
  - `absorption_to_reversal_preparation`
- append-only 输出已覆盖：
  - `feature_slice_v1`
  - `regime_posterior_v1`
  - `event_hypothesis_state_v1`
  - `belief_state_snapshot_v1`
  - `event_episode_v1`
  - `episode_evaluation_v1`
- 关键输出统一携带：
  - `schema_version`
  - `profile_version`
  - `engine_version`
  - 尽可能携带 `data_status` / `freshness` / `completeness`

### Review / Tuning

- `EpisodeEvaluationService` 产出 `episode_evaluation_v1`
- `TuningAdvisorService` 产出 `tuning_recommendation_v1`
- `ProfilePatchCandidate` / `ProfilePatchValidationResult` 已有模型与持久化
- AI 只在 review/tuning 辅助层，不进入线上识别关键路径

### Replay / Projection

- replay workbench snapshot / cache / live tail 已可用
- workbench review projection 已可用：
  - `/api/v1/workbench/review/projection`
  - `/api/v1/workbench/review/belief-state-timeline`
  - `/api/v1/workbench/review/event-episodes`
  - `/api/v1/workbench/review/episode-evaluations`
  - `/api/v1/workbench/review/tuning-recommendations`
  - `/api/v1/workbench/review/profile-engine`
  - `/api/v1/workbench/review/health-status`
- 兼容性 alias 已补齐：
  - `GET /api/v1/belief/latest`
  - `GET /api/v1/episodes/latest`
  - `POST /api/v1/review/episode-evaluation`
  - `GET /api/v1/review/episode-evaluation/{episode_id}`
  - `GET /health/recognition`

## 当前仍未闭环的 backlog

以下项目仍属于 Master Spec v2 backlog，而不是本次收口新增方向：

- `POST /api/v1/rebuild/belief`
- `POST /api/v1/tuning/recommendation`
- `POST /api/v1/tuning/patch/validate`
- `POST /api/v1/tuning/patch/promote`
- 真正的 offline replay compare runner 与 patch promotion 流程

当前仓库已经有对应模型与服务基座，但尚未把这些端点全部作为稳定 HTTP 合同暴露。

## 命名与版本约定

### Canonical schema/version names

- `instrument_profile_v1`
- `recognizer_build_v1`
- `feature_slice_v1`
- `regime_posterior_v1`
- `event_hypothesis_state_v1`
- `belief_state_snapshot_v1`
- `event_episode_v1`
- `episode_evaluation_v1`
- `tuning_recommendation_v1`

### Degraded mode

仓库 canonical 输出使用：

- `degraded_no_depth`
- `degraded_no_dom`
- `degraded_no_ai`
- `degraded_stale_macro`
- `replay_rebuild_mode`

说明：

- Master Spec v2 在 7.3A 段落里保留了旧字样 `bar_anchor_only`
- 同一规格在异常场景与 degraded 枚举章节又使用 `degraded_no_depth`
- 当前仓库选择 `degraded_no_depth` 作为 canonical 输出
- 读取层仍兼容旧值 `bar_anchor_only`

## Contract Artifacts

- `schemas/` 保存从当前 Pydantic 模型导出的 JSON schema artifacts。
- `samples/contracts/` 保存核心 canonical domain payload 样例。
- `samples/responses/` 保存关键 API/read-model response 样例。
- 生成命令：

```powershell
$env:PYTHONPATH = "$PWD\src"
python .\tools\export_json_schemas.py
```

当前重点对齐的 contract artifacts 包括：

- `instrument_profile_v1.schema.json`
- `recognizer_build_v1.schema.json`
- `feature_slice_v1.schema.json`
- `regime_posterior_v1.schema.json`
- `event_hypothesis_state_v1.schema.json`
- `belief_state_snapshot_v1.schema.json`
- `event_episode_v1.schema.json`
- `episode_evaluation_v1.schema.json`
- `tuning_recommendation_v1.schema.json`
- `replay_workbench_health_status_envelope_v1.schema.json`
- `replay_workbench_projection_envelope_v1.schema.json`

## 运行

### 1. 准备环境

```powershell
New-Item -ItemType Directory -Force -Path .\data | Out-Null
$env:PYTHONPATH = "$PWD\src"
```

本地环境变量请使用仓库根目录的 `.env.example` 作为模板：

- 真实 `.env` 仅供本地开发，不应提交到仓库
- 新增环境变量时，同时更新 `.env.example`

### 2. 启动服务

```powershell
python -m atas_market_structure.server
```

后台启动：

```powershell
.\scripts\start-service-background.ps1
```

说明：

- 当 `ATAS_MS_STORAGE_MODE=clickhouse` 时，标准启动脚本会先自动拉起本地 ClickHouse 并初始化基础表结构。
- 如果你只想保留纯 degraded mode 启动，可显式跳过这一步：

```powershell
.\scripts\start-service-background.ps1 -SkipDatabaseStart
```

打开 replay workbench：

```text
http://127.0.0.1:8080/workbench/replay
```

### 3. 启动本地 ATAS workbench 栈

```powershell
.\scripts\start-atas-workbench.ps1 -AtasExePath "C:\Path\To\OFT.Platform.exe"
```

### 4. 停止后台服务

```powershell
.\scripts\stop-service.ps1
```

## 常用接口

健康检查：

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8080/health
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/health/recognition?instrument=NQ"
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/health/data-quality?instrument=NQ"
```

最新 belief / episodes：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/v1/belief/latest?instrument=NQ"
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/v1/episodes/latest?instrument=NQ&limit=20"
```

生成或读取 episode evaluation：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8080/api/v1/review/episode-evaluation `
  -ContentType "application/json" `
  -Body '{"episode_id":"ep-momentum_continuation-1000"}'

Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/v1/review/episode-evaluation/ep-momentum_continuation-1000"
```

完整 projection：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/v1/workbench/review/projection?instrument_symbol=NQ&window_start=2026-03-23T09:29:00Z&window_end=2026-03-23T10:05:00Z"
```

### SPX 期权归档与自动分析

把下载目录里最新的 `quotedata` CSV 归档到项目 `data/`：

```powershell
python .\scripts\archive_downloaded_options_csv.py --copy --date 2026-03-25
```

归档后直接生成 gamma 分析产物：

```powershell
python .\scripts\archive_downloaded_options_csv.py `
  --copy `
 --date 2026-03-25 `
  --analyze `
  --es-price 5042
```

如果再加 `--ai-analysis`，系统会使用研究型 Markdown prompt 生成更完整的期权结构报告，而不是旧的 6 行口播风格：

```powershell
python .\scripts\archive_downloaded_options_csv.py `
  --copy `
  --date 2026-03-25 `
  --analyze `
  --ai-analysis
```

分析产物默认会一起输出到目标 artifact 目录，包括：

- `*_gamma_map.svg`
- `*_gamma_map.json`
- `*_gamma_map.txt`
- `*_strategy_context.json`
- `*_strategy_context.txt`
- `*_options_report.md`
- `*_options_report_prompt.txt`（仅当启用 AI 报告时生成）

其中 `*_options_report.md` 会嵌入前面生成的图；启用 AI 报告时，文件主体会变成 richer prompt 生成的完整研究报告，并保留结构化附件路径。

默认归档目录结构：

```text
data/s&p500_options/YYYY/YYYY-MM-DD/^spx_quotedata_YYYYMMDD_HH00Z.csv
```

默认分析产物目录：

```text
data/s&p500_options/YYYY/YYYY-MM-DD/gamma_artifacts/
```

也可以通过 HTTP 直接触发一体化归档与分析：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8080/api/v1/options/archive-and-analyze `
  -ContentType "application/json" `
  -Body '{"source_dir":"C:\\Users\\666\\Downloads","data_root":"D:\\docker\\atas-market-structure\\data","date":"2026-03-25","symbol":"spx","copy":true,"es_price":5042}'
```

## 开发顺序

推荐的本地开发顺序：

1. 固定 ontology 与 instrument profile
2. recognition feature/regime/event/belief 主链
3. event episode 与 episode evaluation
4. tuning recommendation / patch validation
5. workbench projection / API / samples / docs
6. rebuild / golden replay / acceptance

## 调参流程

当前仓库采用离线调参闭环：

1. append-only 记录 belief / episode / evaluation
2. 由 `TuningBundleBuilder` 聚合 profile、episodes、evaluations、degradation statistics
3. 由 `TuningAdvisorService` 生成 `tuning_recommendation_v1`
4. 生成 `profile_patch_candidate`
5. 运行 boundary validation
6. 等待 offline replay compare 与人工审批
7. 未完成 replay compare 与人工审批前，禁止 promotion

安全边界：

- `allow_ai_auto_apply` 固定为 `false`
- AI recommendation 只能建议，不能自动生效

## 测试

后端测试：

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests -q --ignore=tests/playwright_event_structured_priority.spec.js --ignore=tests/playwright_replay_ui_fix.spec.js
```

定向回归：

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_recognition_pipeline.py tests/test_tuning_services.py tests/test_sample_validation.py tests/test_golden_replay_cases.py tests/test_workbench_projection_api.py -q
```

Playwright UI：

```powershell
npm install --no-save @playwright/test
npx playwright install chromium
npx playwright test tests/playwright_replay_ui_fix.spec.js --reporter=line
```

## Collector / Docker

ATAS C# collector：

```powershell
dotnet build .\src-csharp\AtasMarketStructure.Adapter\AtasMarketStructure.Adapter.csproj
.\scripts\deploy-collector.ps1 -WaitForAtasExit
```

Docker compose：

```powershell
docker compose -f .\docker-compose.yml up --build -d
```

如果只需要本地 ClickHouse 数据库而不是整套 compose 服务，可以直接运行：

```powershell
.\scripts\ensure-clickhouse.ps1
```

## 仓库结构

- `src/atas_market_structure/`: 应用、识别、评估、调参、projection
- `schemas/`: contract artifacts
- `samples/`: sample payloads 与 golden cases
- `scripts/`: launcher / validate / rebuild scripts
- `tools/`: reusable diagnostics / export / inspection scripts
- `tmp/`: local-only scratch outputs, screenshots, transcripts, pytest artifacts
- `tests/`: unit / integration / replay / sample validation
- `docs/`: architecture / ADR / implementation / recognition / tuning / workbench

## 结构治理

- 不要在仓库根目录提交 `_tmp_*`、`tmp_*`、临时 diff、临时 pytest 输出、一次性诊断脚本。
- `repository.py` 与 `workbench_services.py` 是 compatibility facade only；不要继续向里面堆业务逻辑。
- `app.py` 只负责应用装配、依赖注入、路由注册、生命周期管理。
- 新逻辑优先进入对应 focused module，而不是回流到旧巨石文件。
- 可复用诊断脚本放到 `tools/` 或 `scripts/`；临时输出只放 `tmp/`。
