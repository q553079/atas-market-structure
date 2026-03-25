# Replay Workbench Prompt Trace Design

## Goal

Prompt Trace makes each replay-workbench AI turn traceable without changing the existing AI analysis semantics. It records what the model saw, which prompt blocks were used, what bar window or manual selection was active, and which assistant message owns that trace.

## Object model

- `PromptTrace`
  - additive persisted record keyed by `prompt_trace_id`
  - linked to one assistant `message_id` and one `session_id`
  - carries `analysis_type`, `analysis_range`, `analysis_style`, selected/pinned block ids, attached event ids, prompt block summaries, bar/manual/memory summaries, final prompt snapshots, `model_name`, `model_input_hash`, and additive `metadata`
- `prompt_trace_id` on `ChatMessage`
  - nullable for backward compatibility
  - populated for new assistant replies and stream turns

## Generation flow

1. `ReplayWorkbenchChatService._prepare_reply_turn()` builds the existing model input.
2. Before model execution, `ReplayWorkbenchPromptTraceService.create_prompt_trace()` snapshots:
   - selected and pinned prompt blocks
   - replay window summary when available
   - manual selection and extra context summary
   - session memory / recent-message summary
   - final system prompt and final user prompt
   - truncated expanded snapshot for replay/debug
3. The pending assistant message is updated with `prompt_trace_id`.
4. After reply finalization, `finalize_prompt_trace()` patches the resolved model name and `attached_event_ids`.

## Persistence and API

- SQLite table: `chat_prompt_traces`
- Message linkage: nullable `chat_messages.prompt_trace_id`
- Query APIs:
  - `GET /api/v1/workbench/prompt-traces/{prompt_trace_id}`
  - `GET /api/v1/workbench/prompt-traces?session_id=...`
  - `GET /api/v1/workbench/messages/{message_id}/prompt-trace`

All responses are schema-versioned and additive.

## UI strategy

- Assistant messages expose a `查看 Prompt Trace` action.
- Event cards reuse the same trace via `source_prompt_trace_id`.
- The frontend shows a summary-first drawer/modal:
  - analysis type/range/style
  - blocks and attached events
  - bars / manual selection / memory summaries
  - prompt previews
  - optional expanded snapshot

## Compatibility and overload control

- Old messages remain valid because `prompt_trace_id` is nullable and the UI handles missing traces.
- Attachment handling is summary-only; raw image `data_url` is not persisted in trace snapshots.
- Snapshot text is truncated and marked through `metadata.truncation`.
- Development mode can reveal more raw snapshot detail; production keeps the summary view primary.
