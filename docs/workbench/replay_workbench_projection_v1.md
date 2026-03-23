# Replay Workbench Projection V1

状态：V1  
来源：`docs/k_repair/replay_workbench_master_spec_v2.md`

## 目标

Thread 08 落地的是 replay/workbench 的只读投影层，不是识别逻辑本身。  
belief state、event episode、episode evaluation、tuning recommendation、profile/build metadata、health/degraded status 都从现有持久化层读取，再组装成 timeline-friendly JSON，供：

- Replay Workbench UI
- 无前端时的 review/read API
- 后续离线导出或审计

## 设计约束

- projection 只读，不回写识别状态。
- 不把 deterministic recognition 搬进 UI。
- 即使没有 AI recommendation，belief state / episode / evaluation 仍可独立查看。
- 所有关键对象继续保留 `profile_version`、`engine_version`、`schema_version`。
- degraded / freshness / completeness 直接复用现有 health/data-quality 体系。

## Read API

基础过滤参数：

- `instrument_symbol`：必填
- `window_start`：可选，ISO8601，按市场时间过滤
- `window_end`：可选，ISO8601，按市场时间过滤
- `session_date`：可选，`YYYY-MM-DD`
- `limit`：可选，默认 `100`

### 1. Belief timeline

`GET /api/v1/workbench/review/belief-state-timeline`

返回：

- `current_belief`
- `items[]`
- 每条 belief 的 top regimes / top hypotheses / degraded badges / freshness / completeness

### 2. Event episodes

`GET /api/v1/workbench/review/event-episodes`

返回：

- `items[]`
- 每条 closed episode
- 若存在，附带最新 stored evaluation

### 3. Episode evaluations

`GET /api/v1/workbench/review/episode-evaluations`

过滤语义：

- 不是按 evaluation 写入时刻过滤
- 而是按 evaluation 对应 episode 的 `market_time_start` / `market_time_end` 是否落入窗口过滤

这样 historical replay window 下不会漏掉后来生成的 evaluation。

### 4. Tuning recommendations

`GET /api/v1/workbench/review/tuning-recommendations`

过滤语义：

- 不是按 recommendation 的生成时间过滤
- 而是按 recommendation 内 `analysis_window.from/to` 与 replay window 是否重叠过滤

返回：

- `recommendation`
- 关联 `patch_candidate`
- 关联 `latest_validation_result`
- `patch_candidate_status`

### 5. Current profile / engine metadata

`GET /api/v1/workbench/review/profile-engine`

返回：

- `active_profile`
- `active_build`
- `latest_patch_candidate`
- `latest_patch_candidate_status`
- `latest_patch_validation_result`

### 6. Health / degraded status

`GET /api/v1/workbench/review/health-status`

返回：

- `health`
- `data_quality`
- `latest_belief`

### 7. Combined projection

`GET /api/v1/workbench/review/projection`

这是 workbench UI 默认读取的聚合入口，返回：

- `health_status`
- `metadata`
- `belief_timeline`
- `episode_reviews`
- `episode_evaluations`
- `tuning_reviews`
- `timeline`

`timeline[]` 是 timeline-friendly merged view，当前包含：

- `belief_state`
- `event_episode`
- `episode_evaluation`
- `tuning_recommendation`
- `patch_candidate`
- `health_status`

## 示例请求

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8080/api/v1/workbench/review/projection?instrument_symbol=NQ&window_start=2026-03-23T09:29:00Z&window_end=2026-03-23T10:05:00Z&limit=20"
```

## 示例响应

```json
{
  "query": {
    "instrument_symbol": "NQ",
    "window_start": "2026-03-23T09:29:00Z",
    "window_end": "2026-03-23T10:05:00Z",
    "session_date": null,
    "limit": 20
  },
  "health_status": {
    "health": {
      "status": "degraded",
      "degraded_reasons": ["degraded_no_depth", "degraded_no_ai"],
      "profile_version": "nq-profile-test",
      "engine_version": "recognizer-test"
    }
  },
  "metadata": {
    "active_profile": {
      "profile_version": "nq-profile-test",
      "ontology_version": "master_spec_v2_v1"
    },
    "active_build": {
      "engine_version": "recognizer-test",
      "status": "active"
    }
  },
  "belief_timeline": {
    "current_belief": {
      "belief_state_id": "b3-ok",
      "recognition_mode": "normal"
    }
  },
  "episode_reviews": {
    "items": [
      {
        "summary_status": "confirmed / healthy",
        "episode": {
          "event_kind": "momentum_continuation"
        }
      }
    ]
  },
  "episode_evaluations": {
    "items": [
      {
        "primary_failure_mode": "none"
      }
    ]
  },
  "tuning_reviews": {
    "items": [
      {
        "patch_candidate_status": "awaiting_offline_replay"
      }
    ]
  },
  "timeline": [
    {
      "entry_type": "belief_state",
      "title": "belief_state"
    },
    {
      "entry_type": "event_episode",
      "title": "momentum_continuation"
    }
  ]
}
```

## Workbench UI 落点

现有页面未重构，直接增强现有 drawer：

- `Context` drawer：
  - Health / degraded
  - 当前 belief state
  - top regime probabilities
  - top event hypotheses
  - active anchors
  - transition watch
  - missing confirmation
- `Recap` drawer：
  - closed episodes
  - episode evaluation
  - AI recommendation / patch compare
  - current profile / engine metadata

前端读取链路：

- `src/atas_market_structure/static/replay_workbench_replay_loader.js`
  - 在 snapshot/sidebar background load 时追加读取 `/api/v1/workbench/review/projection`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
  - 把 projection 渲染到现有 drawer

## 实现文件

- `src/atas_market_structure/workbench_projection_services.py`
- `src/atas_market_structure/app.py`
- `src/atas_market_structure/repository.py`
- `src/atas_market_structure/storage_repository.py`
- `src/atas_market_structure/models/_replay.py`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_replay_loader.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`

## 测试

已覆盖：

- combined projection endpoint
- belief / episode / evaluation / tuning / metadata / health read APIs
- `session_date` 与 `window_start/window_end` 过滤
- 前端静态资源已引用 projection read path

测试命令：

```powershell
pytest tests/test_workbench_projection_api.py -q
pytest tests/test_tuning_services.py tests/test_app.py -q
```
