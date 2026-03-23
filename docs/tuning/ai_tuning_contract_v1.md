# AI Tuning Contract V1

本文件对应 Master Spec v2 的 Thread 07 落地，定义：

- `tuning_input_bundle_v1`
- `tuning_recommendation_v1`
- `profile_patch_candidate_v1`
- `patch_validation_result_v1`

实现位置：

- `src/atas_market_structure/tuning_services.py`
- `src/atas_market_structure/profile_services.py`
- `src/atas_market_structure/models/_replay.py`

## Scope

V1 的 AI 调参与协作层只做离线顾问，不进入 recognition 关键路径。

输入来源：

- 活跃 `instrument_profile`
- 最近 closed `event_episode`
- 对应 `episode_evaluation`
- 正反样本统计
- patch history
- `recognizer_build`
- belief 层的 degraded statistics

输出对象：

- `tuning_recommendation_v1`
- `profile_patch_candidate_v1`
- `patch_validation_result_v1`

## AI Can Do

- 读取结构化 bundle
- 汇总 top failure modes
- 生成结构化 recommendation
- 生成受边界约束的 patch candidate
- 触发离线 replay validation hook
- 为人工审批准备可审计 payload

## AI Cannot Do

- 不得修改 ontology
- 不得覆盖 `episode_evaluation` 真值
- 不得写回原始 observation
- 不得绕过 boundary validation
- 不得绕过 offline replay validation
- 不得自动 promote profile
- 不得设置 `allow_ai_auto_apply: true`

## Bundle Contract

`tuning_input_bundle_v1` 至少包含：

- `instrument`
- `schema_version`
- `built_at`
- `profile_version`
- `engine_version`
- `analysis_window`
- `instrument_profile`
- `recognizer_build`
- `recent_closed_episodes`
- `episode_evaluations`
- `positive_negative_summary`
- `patch_history`
- `degradation_statistics`
- `unevaluated_episode_ids`

正负样本口径：

- `primary_failure_mode == none` 记为 positive
- 其余记为 negative

降级统计口径：

- 来自 recent belief snapshots 的 `data_status`
- 只做离线顾问输入，不反向污染 recognition

## Recommendation Contract

`tuning_recommendation_v1` 至少包含：

- `recommendation_id`
- `bundle_id`
- `instrument`
- `schema_version`
- `profile_version`
- `engine_version`
- `generated_at`
- `advisor_kind`
- `analysis_window`
- `top_failure_modes`
- `recommendations`
- `expected_improvement`
- `risk`
- `confidence`
- `patch_candidate_ref`
- `allow_ai_auto_apply`

V1 recommendation item 字段：

- `event_kind`
- `parameter`
- `direction`
- `current_value`
- `proposed_value`
- `support_count`
- `reason`
- `expected_improvement`
- `risk`
- `confidence`

## Patch Candidate Contract

`profile_patch_candidate_v1` 沿用现有 patch 基础设施，但在 Thread 07 中统一按以下规则生成：

- append-only 保存
- 记录 `recommendation_id`
- 记录 `base_profile_version`
- 记录 `proposed_profile_version`
- 仅允许可解释参数路径进入 `candidate_parameters`
- 所有 `suggested_changes` 都必须是 from/to 结构
- `allow_ai_auto_apply` 固定为 `false`

参数边界仍由 `InstrumentProfileService.validate_patch(...)` 负责：

- 非法路径拒绝
- 越界拒绝
- step 不合法拒绝
- ontology 字段拒绝
- `safety.allow_ai_auto_apply` 拒绝

## Patch Validation Contract

`patch_validation_result_v1` 在原有 boundary validation 之上增加：

- `schema_version`
- `boundary_validation_status`
- `recommendation_id`
- `base_profile_version`
- `proposed_profile_version`
- `offline_replay_validation`
- `human_approval`
- `promotion_ready`

`offline_replay_validation` V1 先提供 local stub runner：

- `status: not_run | passed | failed`
- `runner`
- `compared_episode_count`
- `metrics`
- `summary`
- `notes`
- `validated_at`

`human_approval` V1 先提供占位：

- `required: true`
- `status: pending | approved | rejected`
- `approved_by`
- `approved_at`
- `notes`

## Safety Gate

所有 patch promotion 前必须经过以下四层：

1. schema validation
2. boundary validation
3. offline replay validation
4. explicit human approval

只要任一层未完成，`promotion_ready` 必须保持 `false`。

## Why Auto Apply Is Forbidden

禁止 auto apply 的原因不是功能未完成，而是设计上明确不允许：

- 避免最近样本过拟合
- 保持可审计
- 保持可回滚
- 避免参数漂移污染历史评估
- 防止 AI 直接控制系统行为

因此：

- `instrument_profile.safety.allow_ai_auto_apply` 固定为 `false`
- `tuning_recommendation.allow_ai_auto_apply` 固定为 `false`
- `profile_patch_candidate.allow_ai_auto_apply` 固定为 `false`
- `patch_validation_result.allow_ai_auto_apply` 固定为 `false`

## Local Runner

当前 `LocalStubOfflineReplayValidator` 的职责是：

- 接收 bundle / recommendation / candidate / boundary validation
- 输出结构化 `offline_replay_validation`
- 明确记录“已进入离线验证流程，但尚未执行 replay compare”

它故意不返回 promotion pass，原因是：

- Thread 07 只落地 scaffold
- 真实 replay compare 仍需单独 wiring
- recognition 关键路径不能依赖该服务
