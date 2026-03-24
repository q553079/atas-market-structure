# Tools

This directory is for committed, reusable utilities only.

Use `tools/` when a script:

- helps inspect repository state or persisted data
- exports artifacts such as JSON schemas
- validates an operational path that another engineer may rerun

Do not use `tools/` for:

- personal scratch scripts
- temporary diffs or pytest output
- screenshots, media, or ad hoc transcript files

Naming guidance:

- `export_*`: artifact generation
- `inspect_*`: read-only repository/data inspection
- `verify_*`: focused operational or contract verification
- `cleanup_*`: repository/sample hygiene utilities

Disposable debugging output belongs in `tmp/`, not here.
