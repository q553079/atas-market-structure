# ATAS Market Structure Module Boundaries

Core recognition mainline must stay:

`observation -> feature slice -> regime posterior -> event hypotheses -> memory anchors -> belief state -> event episode -> episode evaluation -> tuning recommendation`

This repository is not:

- a static label recognizer
- a pure AI black-box classifier
- an auto-trading executor
- a frontend-only project

Dependency direction:

- `app.py` and `app_routes/` depend on service modules only.
- service modules depend on repository/model modules.
- repository modules own persistence and do not depend on routes.
- chat/review/tuning stay outside the deterministic recognition critical path.
- AI may review, explain, replay, or suggest tuning. AI must not decide live recognition outputs.

Workbench split rules:

- `workbench_projection_services.py` owns read-model assembly only.
- `workbench_replay_service.py` owns replay snapshot/cache/live/backfill orchestration.
- `workbench_review_service.py` owns episode/evaluation/recommendation aggregation.
- `workbench_chat_service.py` owns chat session/message/annotation/memory summary flows.
- `workbench_services.py` is a compatibility facade only; do not add business logic there.

Repository split rules:

- `repository_raw_ingestion.py` owns append-only raw ingestion and reliability logs.
- `repository_recognition.py` owns belief/episode/evaluation/profile/build state.
- `repository_projection.py` owns projection/read-model query surfaces.
- `repository_evaluation_tuning.py` owns recommendations, patch validation, promotion lineage.
- `repository_chat.py` owns chat sessions/messages/annotations/memory.
- `repository.py` and `repository_protocols.py` are compatibility facades only.

Large-file anti-regrowth rules:

- New logic must go to the nearest domain module first, not back into a historical giant file.
- If a file is above the soft limit, evaluate split before adding logic.
- If a file is above the hard limit, do not append large new blocks there; move logic sideways.
- Use `scripts/check_file_size_budget.py` and `tests/test_file_size_budget.py` as the ratchet.
