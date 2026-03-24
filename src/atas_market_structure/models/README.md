# Model Package Boundaries

Models in this package define stable schemas, enums, and transport/domain payloads.

Allowed here:

- typed envelopes
- schema/versioned payload models
- enums and small shared value objects

Not allowed here:

- service orchestration
- repository access
- route dispatch
- AI-driven recognition decisions

Guidance:

- Preserve the V1 event ontology.
- Add fields/phases/state transitions only when compatible with existing contracts.
- Prefer adding a focused sibling module over expanding a mega-model file.
- Avoid circular imports between model modules and service/repository modules.
- Freeze canonical `schema_version` outputs here; compatibility reads may accept legacy `1.0.0`, but new writes must emit canonical `*_v1`.
- Keep append-only recognition contracts in focused modules such as `_recognition_contracts.py`; do not push more contract surface back into `_replay.py` or `_responses.py`.
