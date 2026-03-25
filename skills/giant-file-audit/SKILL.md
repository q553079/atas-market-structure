# Giant file audit

Use this skill when the repository shows signs of file-size bloat, mixed responsibilities, or recurring merge conflicts around a few core files.

## Goal
Produce a practical giant-file audit that identifies:
- the largest files
- which files are truly risky
- which files are acceptable for now
- which files are compatibility facades that must not grow again
- a split priority list (P0/P1/P2)

## Workflow
1. Scan `src/`, `tests/`, and relevant frontend/static directories.
2. Estimate line counts.
3. List the largest files.
4. Judge whether each file has mixed responsibilities.
5. Classify files:
   - P0: split now
   - P1: split this round if touched
   - P2: monitor only
6. Propose target modules and responsibility boundaries.
7. Propose anti-regrowth rules.

## Output shape
Return:
- current giant-file list
- risk analysis by file
- split recommendations
- prevention rules
- suggested test/CI guardrails

## Constraints
- Do not rewrite the architecture during the audit.
- Prefer domain-based splits over arbitrary utility dumping.
- Preserve compatibility with lightweight facades where needed.
