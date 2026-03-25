# code_review.md

## Must flag immediately
- New business logic added to compatibility facade files
- AI logic moved into recognizer critical path
- Contract/schema rename without migration note
- Read-path code mutating write-path state
- Giant-file growth without split plan
- New degraded mode names added without tests and docs

## Strong warnings
- Mixed domain DTO/model files with unrelated objects
- New routes without contract tests
- Replay/projection behavior changed without rebuild consistency checks
- Evaluation/tuning objects added without version lineage
- Chat/annotation logic leaking into recognition or persistence core

## Preferred outcomes
- Smaller modules with explicit responsibilities
- Stable contracts with explicit `schema_version`
- Tests layered as contract, domain, integration, degraded-mode
- Minimal diffs that preserve current behavior
