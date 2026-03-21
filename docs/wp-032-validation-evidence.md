# WP-032 Validation Evidence
Date: 2026-03-21

## Pre-flight notes

Service was running but with stale code (no `--reload` flag). The `GET /memory/wake-up` response was missing `strand_id` from all memory items and missing `topic_memories` from the top-level response, because the process had been started before the WP-032 fixes were applied. Restarting the service resolved both issues. This is recorded as a gap (see below).

All validations were run against the live stack: Memgraph (Docker) + FastAPI (uvicorn) + `memory_client` CLI.

## Criteria checklist

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| 1 | wake-up returns non-empty briefing grouped by strand | PASS | 15 memories across 8 strand groups + 1 `(no strand)` group; `### Core context` section present |
| 2 | briefing memory referenced during session | PASS | memory ID: `217c7612-30f9-450a-812d-e5cc7612-...` (strand-companion-current-projects) |
| 3 | memory added using strand ID from list-strands | PASS | strand: `strand-core-work-career`, memory ID: `5af5b600-c384-464a-938e-5ebcf6d2bf21` |
| 4 | close-session scaffold produced add-memory call | PASS | Scaffold produced 4 `memory add-memory` call templates; answered Q4; memory ID: `36de135b-cf6c-4c16-8d67-1290f36024a4` |
| 5 | close-out memory appears in next wake-up | PASS | Confirmed via `wake-up --limit 30` and `search-memory "WP-032 companion session"` |

## Criterion 1 detail

`memory wake-up --topic "graph memory fabric"` output:
- Heading: `## Memory briefing — graph memory fabric`
- Section: `### Core context` present
- Memories grouped by strand IDs: `(no strand)`, `strand-companion-ai-anchor`, `strand-companion-current-projects`, `strand-companion-human-anchor`, `strand-companion-memory-macro`, `strand-companion-protocols-systems`, `strand-core-family`, `strand-shadow-boundaries`, `strand-shadow-current-stressors`
- `### Relevant to today` section: not rendered — correct, because with only 15 total memories the topic-vector results were a strict subset of the core (importance-ranked) list; topic_memories returned empty by the API as designed

## Criterion 4 detail

`memory close-session` produced:
```
## Session close-out — 2026-03-21 13:06 UTC
Review this session and answer the following before ending:
1. What decisions were made? (store as type: decision)
2. What was learned or observed about the user? (store as type: insight or observation)
3. What actions were committed to? (store as type: todo)
4. What context should a future session know that isn't already in the fabric?
```
Answered question 4 with a `fact` type memory on `strand-core-work-career`.

## Gaps and findings

**Gap 1 — Stale service on session start (operational friction):**
The uvicorn process was started without `--reload` before the WP-030/WP-032 code was the live version on disk, so `strand_id` and `topic_memories` were absent from the API response. The issue is invisible without a comparison baseline — the CLI printed no error, it simply grouped everything as `(no strand)`. Restarting the service fixed it.
- Mitigation: document in WIRING.md that the service must be restarted (or run with `--reload`) after code updates.
- Backlog candidate: add a version/build hash to the `/health` endpoint so the client can detect mismatches.

**Gap 2 — `### Relevant to today` only useful with larger DB:**
With a small DB (15 memories), all topic-relevant results are already in the importance-ranked core list, so the topic section never renders. This is correct behaviour but could confuse a companion who expects the section to always appear when `--topic` is given.
- Mitigation: document the expected behaviour in COMPANION.md.

**Gap 3 — No strand ID returned on `add-memory`:**
The CLI `add-memory` command returns only the memory UUID. During validation, the companion must remember which strand was used in order to reference it. If the strand ID is forgotten, `search-memory` or a separate query is needed to recover it.
- Backlog candidate: return strand_id(s) alongside the memory ID in the `add-memory` response.

**Gap 4 — `(no strand)` memories visible without strand filtering:**
Legacy memories seeded without a strand ID (including two `db down test` entries) appear in the briefing under `(no strand)`. These pollute the briefing.
- Mitigation: clean up test/debug memories; optionally add a `--exclude-no-strand` flag to wake-up.

## Backlog items to add

| ID | Title | Priority | Notes |
|----|-------|----------|-------|
| WP-034 | Add version/build hash to `/health` response | L/S | Detect stale service during companion session startup |
| WP-035 | Return strand_ids in `add-memory` API response | L/S | Reduce friction when adding chains of related memories |
| WP-036 | Document `### Relevant to today` absence behaviour in COMPANION.md | L/S | Avoid companion confusion when topic section is suppressed |
