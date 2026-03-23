# Acceptance And Regression

本文件对应 Master Spec v2 对“可验证、可回放、可回归”的要求，覆盖 golden replay、sample contract、rebuild consistency、degraded mode、以及 AI 不在识别关键路径上的验收口径。

## 覆盖范围

- Golden replay cases 存放在 `samples/golden_cases/`。
- Golden case schema / materializer 在 `src/atas_market_structure/golden_cases.py`。
- Rebuild / replay runner 在 `src/atas_market_structure/rebuild_runner.py` 与 `scripts/rebuild/run_replay_rebuild.py`。
- Sample validation 在 `src/atas_market_structure/sample_validation.py` 与 `scripts/validate/validate_samples.py`。
- Acceptance tests 主要分布在：
  - `tests/test_golden_replay_cases.py`
  - `tests/test_rebuild_runner.py`
  - `tests/test_sample_validation.py`
  - 以及既有的 ingestion / recognition / evaluation / tuning / migration / workbench API tests

## Golden Case 说明

当前 golden cases 分四组：

- `momentum_continuation.case_set.json`
  - 3 个正常闭环 case
  - 最终要求 `top_event_kind=momentum_continuation`
  - 至少 1 个 closed episode 和 1 个 `episode_evaluation_v1`
- `balance_mean_reversion.case_set.json`
  - 3 个正常 case
  - 重点验证 balance hypothesis、anchor、freshness / completeness 字段
- `absorption_to_reversal_preparation.case_set.json`
  - 3 个正常 case
  - 重点验证 absorption / reversal-prep hypothesis 在 deterministic path 上可输出
- `degraded_and_failure.case_set.json`
  - `degraded_no_depth`
  - `degraded_no_ai`
  - `degraded_stale_macro`
  - `missed_transition`

每个 case 都显式声明：

- 输入 steps
- `ai_available`
- 期望的 `top_event_kind`
- 期望的 `recognition_mode`
- 必须存在或禁止存在的 degraded modes
- episode / evaluation 最小数量
- completeness / freshness

## 运行方式

验证全部 samples：

```powershell
python .\scripts\validate\validate_samples.py
```

运行所有 golden replay cases：

```powershell
python .\scripts\rebuild\run_replay_rebuild.py `
  --golden-cases .\samples\golden_cases `
  --overwrite
```

只跑一个 golden case：

```powershell
python .\scripts\rebuild\run_replay_rebuild.py `
  --golden-cases .\samples\golden_cases `
  --case-id failure_missed_transition_04 `
  --output-db .\data\rebuild\failure_missed_transition_04.db `
  --overwrite
```

从现有 SQLite 原始库做 rebuild：

```powershell
python .\scripts\rebuild\run_replay_rebuild.py `
  --source-db .\data\market_structure.db `
  --instrument NQ `
  --session-date 2026-03-23 `
  --page-size 5000 `
  --output-db .\data\rebuild\nq-20260323.db `
  --overwrite
```

从 ClickHouse raw ingestions 做 rebuild：

```powershell
$env:ATAS_MS_CLICKHOUSE_HOST = "127.0.0.1"
$env:ATAS_MS_CLICKHOUSE_PORT = "8123"
$env:ATAS_MS_CLICKHOUSE_DATABASE = "market_data"
$env:ATAS_MS_CLICKHOUSE_INGESTIONS_TABLE = "ingestions"

python .\scripts\rebuild\run_replay_rebuild.py `
  --source-clickhouse `
  --metadata-db .\data\market_structure.db `
  --instrument NQ `
  --session-date 2026-03-23 `
  --page-size 2000 `
  --output-db .\data\rebuild\nq-clickhouse-20260323.db `
  --overwrite
```

注意：

- repository replay 默认 `AI unavailable`，因为 AI 不应在关键路径上。
- 如果只是为了复现实盘“AI 可用”的 freshness / degrade 标签，可以显式加 `--ai-available`。
- rebuild runner 输出的是 fresh target DB，不会在原库上做 destructive replay。
- `--source-clickhouse` 只把 raw ingestion source 切到 ClickHouse；deterministic rebuild target 仍然是 fresh SQLite。
- `--metadata-db` 负责提供 active instrument profile / recognizer build；如果不显式传入，则回退到 `ATAS_MS_DB_PATH` 或仓库默认 SQLite 路径。
- `--page-size` 用于 repository replay 的 source 分页读取；ClickHouse 大窗口回放应显式设置，避免单次查询过大。

## 测试命令

建议的 acceptance suite：

```powershell
pytest `
  tests/test_app.py `
  tests/test_ingestion_reliability.py `
  tests/test_recognition_pipeline.py `
  tests/test_episode_evaluation.py `
  tests/test_tuning_services.py `
  tests/test_storage_migrations.py `
  tests/test_storage_blueprint_repository.py `
  tests/test_workbench_projection_api.py `
  tests/test_golden_replay_cases.py `
  tests/test_rebuild_runner.py `
  tests/test_sample_validation.py `
  -q
```

快速只看本线程新增内容：

```powershell
pytest `
  tests/test_golden_replay_cases.py `
  tests/test_rebuild_runner.py `
  tests/test_sample_validation.py `
  -q
```

## 失败定位

如果 `validate_samples.py` 失败：

- 先看 `path`
- 再看 sample 是否仍符合当前 pydantic contract
- 如果是 `samples/golden_cases/` 失败，优先检查 step schema 是否与 materializer drift

如果 `test_golden_replay_cases.py` 失败：

- 看 `ReplayRebuildRunner.validate_case_report(...)` 返回的哪条 expectation mismatch
- 再看 runner 输出里的 `step_outcomes`
- 常见原因：
  - top event 改变
  - degraded mode 多出或缺失
  - 某一步没有生成 episode / evaluation

如果 `test_rebuild_runner.py` 的 consistency 失败：

- 对比两个 report 的 `step_outcomes`
- 看是否有 step 顺序不稳定
- 看是否有 ID / timestamp 仍依赖 wall-clock 而不是 replay step

如果 `degraded_no_ai` case 失败：

- 说明识别链路错误地依赖了 AI availability
- 这是高优先级回归，必须优先修复

如果 `missed_transition` case 失败：

- 先看 `event_episode` 是否还在正确地产出 `replaced`
- 再看 `episode_evaluation_v1` 是否还识别 `missed_transition`

## CI

CI workflow 在 `.github/workflows/acceptance-and-regression.yml`，固定执行：

- `ruff check src tests scripts`
- `mypy` 目标检查：
  - `src/atas_market_structure/golden_cases.py`
  - `src/atas_market_structure/rebuild_runner.py`
  - `src/atas_market_structure/sample_validation.py`
- `python scripts/validate/validate_samples.py`
- acceptance pytest suite

这样可以把：

- schema drift
- golden case drift
- replay rebuild drift
- degraded mode drift
- AI critical-path regression

都尽量前置到 CI。
