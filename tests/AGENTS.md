# AGENTS.md

## Test rules
- Prefer contract/domain/integration/degraded-mode layering.
- Do not dump all new tests into a single giant file.
- When changing routes, add contract tests.
- When changing recognizer/evaluation behavior, add domain tests.
- When changing rebuild/projection behavior, add integration tests.
- When changing availability/degraded behavior, add explicit degraded-mode tests.
- Do not hide contract changes only inside broad integration tests.

## Test expectations
- Prefer keeping contract coverage near route or API surface changes.
- Prefer keeping domain coverage near recognizer, evaluation, and tuning behavior changes.
