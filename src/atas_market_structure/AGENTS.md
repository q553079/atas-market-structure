# AGENTS.md

## Backend rules
- Do not move AI into recognizer critical path.
- Preserve append-only write behavior.
- Preserve degraded mode behavior.
- Preserve rebuildability of read models.
- Prefer splitting by domain:
  recognition / projection / evaluation / tuning / replay / chat
- Do not reintroduce giant service files.
- If you touch a file above the soft limit, evaluate splitting before adding logic.
- Old facade files may re-export or bridge imports only.

## Dependency direction
- routes -> services -> repository/models
- repository must not depend on routes
- projection/read helpers must not mutate write-path state
- chat/review/tuning must not leak back into recognizer core

## Required checks after changes
- relevant unit/integration tests
- import sanity
- no obvious circular dependencies
