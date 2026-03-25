# AGENTS.md

## Model rules
- Keep schema names stable.
- Every externally returned model must carry schema_version when applicable.
- Split model files by domain when class density grows.
- Do not mix unrelated DTOs in one file.
- If a compatibility model alias is required, document why.
- Do not silently delete or rename externally visible payload fields.

## Suggested domain split
- observation/raw mirror
- feature/regime/hypothesis
- belief/episode/evaluation
- tuning/profile/version lineage
- replay/projection transport
- API responses/health
