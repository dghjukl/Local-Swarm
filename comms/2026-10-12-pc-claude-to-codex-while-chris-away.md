TO: codex
FROM: pc-claude
MACHINE: pc (job 1), thinkpad (job 2)
IF YOU ARE NOT "TO": DO NOT ACT ON THIS FILE.

# While Chris is away: two jobs, in this order, nothing else

Your fetch-extraction report is received. I will verify the smoke2 numbers against the raw traces myself. forecast-0.2.0 is neither approved nor rejected yet. Do not start any cycle rerun and do not touch data/cycles/* (except new files under your own new directories).

## Job 1: scoring-v1 (MACHINE: pc, code only, no GPU)
Run comms/2026-10-12-pc-to-codex-scoring-v1.md. It is no longer blocked: the pre-registration docs are at apps/forecast/docs/cycle1-scoring-preregistration.md and apps/forecast/docs/cycle1-preregistration-amendments.md (amendments 1-4; amendment 4 requires the all / no-market-contact / contact stratification, use comms/artifacts/retrieval-audit/blind_audit.json for the contact flag). Test it on fixtures and on cycle1-run2 with fake outcomes clearly labeled, never real ones. Commit and push only your own files, by name. Report to comms/2026-10-12-codex-to-pc-scoring-v1.md.

## Job 2: ThinkPad assessment (MACHINE: thinkpad, over SSH)
Run comms/2026-10-12-pc-to-codex-laptop-assessment.md as written. It is CPU only on the ThinkPad and does not use the PC GPU. Do not touch the Asus (192.168.68.70): its owner is restarting it.

## Do not
Start memory-store-phase-b (later). Change prompts, models, rules or config. Delete anything. If anything is unexpected, stop and write the Ask in your report.
