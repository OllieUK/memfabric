# WP-079 — Importance Recalibration Pass

**Date:** 2026-03-28

## Goal

Recalibrate all active memories currently rated `importance >= 4` so they match the blast-radius-of-absence model documented in `memory_client/COMPANION.md`.

This is a live data pass, not a code change.

## Constraints

- Review only active memories.
- Apply the new definition literally:
  - `5` = breach if absent
  - `4` = significant miss if absent
  - `3` = quality loss if absent
  - `2` = supplementary / barely noticeable if absent
- Default to downgrading when the higher bar is not clearly met.
- Preserve existing memory content; update `importance` only.

## Approach

1. Export all active `Memory` nodes with `importance >= 4`, including strand, type, fact, `so_what`, and operational metadata.
2. Review them in batches against the new definition.
3. Keep `5` only for active safety, boundary, identity, or protocol memories where absence would cause a real breach.
4. Keep `4` only for live project constraints, active communication rules, or context whose absence would produce a materially wrong outcome.
5. Move the majority to `3`, and supplementary background/history to `2`.
6. Apply updates directly in Memgraph.
7. Verify post-pass counts and spot-check the surviving `4`/`5` population.

## Testing Strategy

The repository-level `engineering:testing-strategy` skill referenced by `CLAUDE.md` is not available in this Codex session, so this work package uses a local verification plan appropriate to a data-only mutation:

- Pre-flight query: count active memories at `importance >= 4`
- Mutation verification: confirm all intended nodes were updated without changing non-targeted fields
- Post-flight query: compare before/after importance distribution
- Spot checks:
  - surviving `importance = 5` memories are genuine breach-level anchors
  - surviving `importance = 4` memories are materially outcome-shaping
  - downgraded project/history/background memories no longer crowd the wake-up tier

## Acceptance Criteria

- Every active memory previously at `4` or `5` has been reviewed once against the new definition.
- The live graph reflects the recalibrated importance values.
- The remaining `5` set is small and clearly boundary / breach level.
- The remaining `4` set is materially smaller than before and dominated by active constraints rather than generic context.
