# WP-138 — Calibrate Threat Deduplication Threshold

> **Plan file:** `docs/plans/wp138_threat_dedup_calibration.md`
> See `docs/plans/wp126_post_tool_use_hook.md` as a reference sibling.

---

## Context — why this change is being made

WP-108 delivered the threat report ingestion pipeline with a conservative cosine-distance
dedup threshold of **0.15** hardcoded in `scripts/extract_cti_threats.py:235`. The live
ingestion run over five English CTI reports (Verizon DBIR 2025, ENISA ETL 2025, Mandiant
M-Trends 2026, Microsoft DDR 2025, Cloudflare 2026) produced **364 Threat nodes** but
deduplicated only **7** of them (1.9%) — despite every report covering the same core
techniques (T1486 ransomware, T1566 phishing, T1110 brute-force / credential access).

Diagnosis, confirmed by live probe against `POST /knowledge/search/threats`:

- Semantically equivalent threats from different reports sit at cosine distance **~0.20–0.37**,
  not `<0.15`.
- Example: a query for *"ransomware encrypted hospital files"* returns top-3 hits at
  distances **0.340, 0.366, 0.369** — all ransomware-related, all above the current cutoff.
- Example: a generic *"ransomware"* query returns top-5 hits at **0.257–0.272**.

Root cause: the 0.15 default was set as a safety placeholder during WP-108 without
empirical calibration. It merges only near-exact duplicates and lets ~98% of
cross-report paraphrases through as distinct nodes, polluting the Threat corpus.

**Intended outcome:** a new default cosine-distance threshold, chosen from empirical
self-similarity analysis of the current 364-threat corpus, that merges clear
cross-report paraphrases of the same attack while keeping genuinely distinct threats
(e.g. credential-access precursors vs. encryption execution) separate. Deliverable is a
small calibration script plus the new default, committed with a one-paragraph evidence
note appended to the WP-108 retrospective.

**Hypothesis band from WP-138 brief:** 0.25–0.30. **Adjusted post-probe expectation:**
0.20–0.30 — the upper end of the original band risks over-merging related-but-distinct
techniques (e.g. T1110 credential stuffing vs T1486 encryption payloads in the same
ransomware campaign). The calibration histogram will settle this empirically.

Scope constraint: WP-138 is a **spike**. No schema changes, no new endpoints, no new
env vars, no matplotlib, no external dependencies.

---

## Deliverables

### Files to create
1. `scripts/calibrate_threat_dedup.py` — calibration script (direct Bolt, reads
   `Threat.embedding`, prints within/between distance histograms, auto-recommends a
   threshold, simulates a pair-rerun on Verizon+ENISA without touching the graph).
2. `tests/test_wp138_threat_dedup_calibration.py` — one unit test on the pure
   `classify_pairs` function, plus two `@pytest.mark.integration` subprocess tests.

### Files to modify
3. `scripts/extract_cti_threats.py` — line **235** default bumped from `0.15` to the
   calibrated value; line **16** docstring updated; one-line calibration comment added
   above line 235 referencing WP-138 and the embedding model.
4. `BACKLOG.md` — one-paragraph calibration note appended to the WP-108 retrospective
   at **line 1252** (after "worked well — no manual YAML curation required.").

### Files NOT touched
- `scripts/ingest_all_threat_reports.py` — the orchestrator does not hardcode a
  threshold; it subprocess-spawns `extract_cti_threats.py` without `--dedup-threshold`,
  so bumping the extractor default propagates automatically. Explicit verification
  step in the work order confirms this.
- `memory_service/knowledge_routes.py`, `memory_service/config.py`, `.env.example`,
  `memory_repo.py` — unchanged per scope constraint.

---

## Critical files referenced

| File | Lines | Role |
|------|-------|------|
| `scripts/extract_cti_threats.py` | 16, 200–213, 235, 307 | Current dedup default + call site |
| `scripts/ingest_all_threat_reports.py` | 16, 109–129 | Orchestrator (no default stored) |
| `scripts/create_cross_framework_informs.py` | 91–122, 187–188, 220–237 | Reuse: `compute_histogram`, `cosine_similarity_matrix`, `_print_histogram` |
| `scripts/dedup_cleanup.py` | 23, 27–28, 31–43, 125–139 | Pattern: direct Bolt + `memory_service.config.Settings`, CLI `--similarity-threshold` |
| `memory_service/knowledge_routes.py` | 443–453, 946–964 | `ThreatSearchRequest`, `ThreatHit`, endpoints |
| `memory_service/knowledge_repo.py` | 863–872, 889, 901–914 | `upsert_threat`, `list_threats`, `search_threats` |
| `memory_service/config.py` | 47, 53 | `memory_dedup_threshold=0.05`, `knowledge_embedding_model` |
| `scripts/init_knowledge_schema.py` | 89, 237–254 | `threat_embedding_idx` creation (cos, 384-dim) |
| `tests/test_wp088_dedup_enforcement.py` | 233–254 | Subprocess integration-test pattern to follow |
| `BACKLOG.md` | 21 (WP-138 entry), 1237–1252 (WP-108 retrospective — note append site) | Context + calibration note destination |

### Reused infrastructure (no duplication)
- `compute_histogram(values, bin_width, low, high)` → `create_cross_framework_informs.py:91-122`
- `cosine_similarity_matrix(embeddings)` → `create_cross_framework_informs.py` (L2-normalised, handles zero-norm rows)
- `memory_service.config.Settings` + `get_driver(settings)` → `memory_service/config.py`
- `memory_service.memory_repo.cosine_similarity` → canonical Python-side cosine

---

## Design decisions

### D1. Transport: direct Bolt, not HTTP
Need `Threat.embedding` for all 364 nodes once (not 364 HTTP probes).
`GET /knowledge/threats` omits embeddings; re-embedding 364 texts through
`/knowledge/search/threats` would be wasteful and semantically lossy. Follow the
`dedup_cleanup.py` / `create_cross_framework_informs.py` pattern: `get_driver(Settings())`,
single Cypher fetch, in-process numpy matrix.

### D2. Pair classification: `tag-overlap` default, `dominant-three` cross-check
`classify_pairs(threats, mode)` returns `(within_distances, between_distances)`:

- **`tag-overlap`** (default): pair is "within" iff the two threats share ≥1 ATT&CK
  technique tag. High volume (~66k pairs), smooth histograms, robust to extractor noise.
- **`dominant-three`**: only pairs where both endpoints carry at least one of
  `{T1486, T1566, T1110}` (the techniques confirmed to appear in all five reports).
  Lower volume, higher precision on the "same attack" definition.

**Rule**: run both modes. If the auto-recommendations agree within 0.03, adopt the
`tag-overlap` figure (larger sample). If they disagree, favour `dominant-three`
(precision over volume) and document the split in the calibration note.

Tagless threats (empty `tags` list) only contribute to the between-cluster pool,
never to within — a pair needs overlap on both sides to be "within".

### D3. Threshold selection: p90/p10 auto-recommendation, **refuses** on no-gap
Auto-rule in `_auto_recommend(within, between) -> RecommendResult`:

```python
@dataclass
class RecommendResult:
    threshold: Optional[float]   # None if no clean gap
    status: Literal["clean_gap", "no_gap_manual_required", "clamped"]
    clamped: bool
    warning: Optional[str]
    within_p90: float
    between_p10: float
```

1. Compute `within_p90` and `between_p10`.
2. If `within_p90 < between_p10` (clean gap): `threshold = round((within_p90 + between_p10) / 2, 2)`,
   status `clean_gap`.
3. If overlapping (`within_p90 >= between_p10`): **return `threshold=None`**, status
   `no_gap_manual_required`, warning `"no clean p90/p10 gap (delta=<x>); manual decision
   required — inspect histograms"`. The CLI exits with code 2 in `--recommend` mode and
   prints a clear "manual decision required" banner in `--histogram` mode. **The script
   does not guess.** This mitigates pre-mortem F1 (noise-driven fallback).
4. If clean gap but threshold falls outside `[0.18, 0.32]`: clamp and set status `clamped`,
   warning explains which boundary was hit. The implementer must justify or override.

Why p90/p10 not max/min: expected 5–10% OCR-noise tail would collapse max/min gaps.
Percentiles are the robust choice for a noisy corpus — see also F4 mitigation via
`--exclude-noise` flag.

The recommendation is a hint even when it exists. The implementer reads the histograms,
runs the pair-rerun simulation, **validates the classifier on 20 hand-labelled pairs**
(see §Pre-mortem F2 mitigation), and commits the final chosen value. The chosen value
must be justified in the commit message and the calibration note.

### D4. Pair-rerun: in-process simulation, not extractor re-run
**The existing `extract_cti_threats.py --dry-run` path at line 307
(`existing_id = None if args.dry_run else find_duplicate_threat(...)`) skips the dedup
lookup entirely in dry-run mode.** It reports `Deduplicated: 0` regardless of threshold.
It is therefore unusable for calibration.

Instead, `--pair-rerun` reads all Threats from the two named reports (default Verizon +
ENISA) via Cypher on the `(:ThreatReport)-[:IDENTIFIES]->(:Threat)` edge, sorts them
by `created_at` to mirror real ingestion order, and greedily simulates
`find_duplicate_threat` against a growing `seen` set. Reports canonical count, merged
count, merge uplift vs the 0.15 baseline, and the top 10 "new" merges (pairs that merge
at the candidate threshold but not at 0.15) so the human reviewer can eyeball false
positives.

Memgraph is never mutated. The simulation does not exercise IDENTIFIES / MAPPED_TO_TECHNIQUE
edge creation, but those paths are threshold-independent so skipping them is safe.
Calibration note must explicitly acknowledge this gap.

### D5. Orchestrator passthrough: deferred
`ingest_all_threat_reports.py:109-129` builds its subprocess command without passing
`--dedup-threshold`, so the extractor's argparse default (line 235) is what runs. Bumping
that default propagates automatically — no orchestrator edit required. A future WP can
add orchestrator-level passthrough for runtime override if needed; WP-138 should stay
focused on the calibration evidence.

### D6. One-line model-binding comment
Above `extract_cti_threats.py:235`, add:
```python
# Calibrated for paraphrase-multilingual-MiniLM-L12-v2 (WP-138).
# Re-run scripts/calibrate_threat_dedup.py --histogram and re-tune if the
# knowledge embedding model changes or a new CTI report is ingested.
```
Zero runtime cost; satisfies the "no new config" constraint while pinning the
calibration assumption to source.

---

## CLI interface for `scripts/calibrate_threat_dedup.py`

```
python scripts/calibrate_threat_dedup.py [SUBCOMMAND] [options]

Subcommands (exactly one required):
  --histogram          Within-vs-between distance histograms + auto-recommendation.
  --pair-rerun         Simulate re-ingestion of a report pair at a candidate threshold.
  --recommend          Print only the auto-recommended threshold (no histograms).
  --verify             Compare current committed default against fresh histogram
                       recommendation; exit 1 if drift > 0.03. For re-tune triggers
                       (mitigates F3).
  --sample-for-review N
                       Print N random within-pairs and N random between-pairs with
                       their texts and distances, in plain text for manual labelling.
                       Used in the F2 mitigation step before committing.

Options:
  --bin-width FLOAT            Histogram bin width (default 0.02; finer than the
                               project-standard 0.05 because the interesting region
                               [0.15, 0.40] is only 25 pp wide).
  --range LOW HIGH             Distance range to histogram (default 0.0 0.6).
  --technique-mode {tag-overlap, dominant-three}
                               Pair classification mode (default tag-overlap).
  --exclude-noise              Filter OCR-garbage threats (matching the heuristic) from
                               all computations. Run histograms both with and without
                               this flag; if recommendations disagree by >0.03 the noise
                               is biasing the calibration and the implementer picks
                               explicitly (mitigates F4).
  --threshold FLOAT            Only with --pair-rerun / --verify: threshold to simulate
                               / verify against (default: whatever --recommend produces
                               / current extract_cti_threats.py default).
  --report-ids ID,ID           Only with --pair-rerun: comma-separated ThreatReport IDs
                               (default report-verizon-dbir-2025,report-enisa-etl-2025).
  --json                       Emit a machine-readable JSON block alongside stdout text
                               for the integration test to assert values.
```

### Output: `--histogram`

```
Corpus:         364 Threat nodes
Pairs:          66,066 total  (within: 14,202 / between: 51,864 at --technique-mode tag-overlap)
Bin width:      0.02   Range: [0.0, 0.6]

Within-attack distances (summary):
  mean 0.184   median 0.181   p10 0.092   p90 0.276   min 0.021   max 0.389

Between-attack distances (summary):
  mean 0.412   median 0.419   p10 0.241   p90 0.551   min 0.103   max 0.742

Within-attack histogram:
  0.00-0.02: █ 12
  0.02-0.04: ██ 34
  ...
Between-attack histogram:
  0.00-0.02: 0
  ...

Gap analysis:
  within.p90                   0.276
  between.p10                  0.241
  clean gap?                   NO — within.p90 > between.p10 by 0.035
  recommended threshold        0.27   (fallback: round(within.p90, 2))
  [WARN] no clean p90/p10 gap; run --pair-rerun --threshold 0.27 and inspect
         top merged pairs before accepting.
```

### Output: `--pair-rerun --threshold 0.27`

```
Pair-rerun simulation  report_ids=[report-verizon-dbir-2025, report-enisa-etl-2025]
  Threshold                    0.27
  Total Threats (pair subset)  142
  Canonical (kept)             128
  Merged (dropped)             14
  Baseline (0.15) merges        2
  Merge uplift                 +600%  (14 vs 2)

Top 10 new merges (merged at 0.27, not at 0.15):
  0.198  threat-enisa-...  "Ransomware actors increasingly target..."
         threat-verizon-... "Ransomware operators continue to focus on..."
  0.214  threat-enisa-...  "Phishing campaigns delivered credential..."
         threat-verizon-... "Credential-stealing phishing activity..."
  ...

Noise diagnostic:
  7 of 142 threats (4.9%) flagged as likely OCR garbage
  (heuristic: >3 digits in any 10-char window OR no consecutive vowels)
```

---

## Test plan

Per `CLAUDE.md` working norms, test plan is mandatory and must specify unit vs
integration tests and acceptance criteria up front.

### Unit tests (pure functions, no DB) — parametrised edge cases (F9 mitigation)

`tests/test_wp138_threat_dedup_calibration.py::test_classify_pairs`

Tests `classify_pairs(threats, mode)` across six cases:

| Case | Input | `tag-overlap` expected | `dominant-three` expected |
|------|-------|------------------------|---------------------------|
| base | 4 threats (t1,t2 share T1486; t3=T1110; t4 tagless) | 1 within, 5 between | 1 within, 2 between (t4 excluded) |
| empty | `[]` | `([], [])` | `([], [])` |
| all-tagless | 3 threats with `tags=[]` | 0 within, 3 between | 0 within, 0 between |
| all-same-tag | 3 threats all `tags=["T1486"]` | 3 within, 0 between | 3 within, 0 between |
| zero-norm | 2 threats with zero-vector embedding | raises `ValueError` OR filters | same |
| no-dominant | 2 threats with `tags=["T9999"]` | 1 within, 0 between | 0 within, 0 between |

`test_auto_recommend`:
- **Clean gap case**: within=[0.1,0.2], between=[0.3,0.4] → threshold ≈ 0.25, status `clean_gap`.
- **No-gap case**: within=[0.1,0.4], between=[0.2,0.5] → threshold `None`, status `no_gap_manual_required`. **This is the F1 mitigation in test form.**
- **Clamped case**: within=[0.01], between=[0.05] → threshold would be 0.03, clamped to 0.18, status `clamped`.

`test_simulate_pair_rerun_order_invariance` (F7 mitigation):
- Given 5 threats with known embeddings, assert that `merged_count` is identical
  whether threats are passed in ascending or descending `created_at` order. The
  simulation must sort internally.

`test_ocr_noise_heuristic`:
- `"% 10 Data Theft % Extortion 6"` → True
- `"Ransomware operators target healthcare institutions"` → False
- Empty string → True (conservative)

Runtime: <1s total. No DB, no subprocess.

### Integration tests (subprocess, require live stack) — semantic assertions (F8 mitigation)

Both marked `@pytest.mark.integration`, modelled on `test_wp088_dedup_enforcement.py:233-254`.

**Test 1 — `test_histogram_runs_with_semantic_assertions`:**
```python
result = subprocess.run(
    [sys.executable, "scripts/calibrate_threat_dedup.py", "--histogram", "--json"],
    capture_output=True, text=True, cwd=_PROJECT_ROOT,
)
assert result.returncode == 0, result.stderr
out = result.stdout.lower()
assert "within" in out
assert "between" in out
assert "\u2588" in result.stdout          # histogram bar char present

data = json.loads(_extract_json_block(result.stdout))
# Corpus sanity
assert data["corpus_size"] == 364, f"expected 364, got {data['corpus_size']}"
assert data["within_count"] > 100, "tag-overlap should yield substantial within pairs"
assert data["between_count"] > 1000
# Distribution sanity — both should be non-degenerate and in cosine distance range
assert 0.0 < data["within"]["p90"] < 0.6
assert 0.0 < data["between"]["p10"] < 0.6
assert data["between"]["p10"] > data["within"]["p10"], "between should start higher than within"
# Status must be one of the three known states
assert data["status"] in {"clean_gap", "no_gap_manual_required", "clamped"}
```

**Test 2 — `test_pair_rerun_predicts_uplift`:**
```python
result = subprocess.run(
    [sys.executable, "scripts/calibrate_threat_dedup.py",
     "--pair-rerun", "--threshold", "0.28", "--json"],
    capture_output=True, text=True, cwd=_PROJECT_ROOT,
)
assert result.returncode == 0, result.stderr
data = json.loads(_extract_json_block(result.stdout))
# Simulation must be non-trivial
assert data["merged_count"] > 0
assert data["canonical_count"] > 0
assert data["merged_count"] < data["canonical_count"], "simulation collapsed the corpus (over-merge)"
# Uplift over baseline must be real
assert data["baseline_merged_count"] >= 0
assert data["merged_count"] >= data["baseline_merged_count"]
```

**Test 3 — `test_verify_catches_drift`:**
```python
result = subprocess.run(
    [sys.executable, "scripts/calibrate_threat_dedup.py", "--verify", "--json"],
    capture_output=True, text=True, cwd=_PROJECT_ROOT,
)
# Exit 0 if current default is within 0.03 of fresh recommendation.
# Exit 1 if drift > 0.03 (which is expected behaviour — test documents it).
assert result.returncode in (0, 1)
data = json.loads(_extract_json_block(result.stdout))
assert "current_default" in data
assert "fresh_recommendation" in data
assert "drift" in data
```

None of the three tests mutate the graph.

### Acceptance criteria (all six must hold — F11 mitigation adds #6)
1. `--histogram` output shows within-cluster and between-cluster distributions with
   either a clean p90/p10 gap, or an explicit `no_gap_manual_required` status that
   forces a manual decision (F1).
2. Recommended threshold falls in **[0.18, 0.32]**; if clamped, the calibration note
   explains why.
3. `--pair-rerun` on Verizon+ENISA at the chosen threshold predicts **≥3× more merges**
   than the 0.15 baseline.
4. **Classifier validation (F2):** implementer runs `--sample-for-review 20` and
   manually labels 10 within-pairs and 10 between-pairs. Agreement with the
   tag-overlap classifier must be **≥70%** (14/20). If <70%, WP-138 halts — the
   calibration approach is invalid and the failure is documented in a new backlog
   item escalating to embedding-cluster-based classification.
5. Calibration paragraph appended to `BACKLOG.md` at the WP-108 retrospective (~line
   1252) includes: `n=364`, technique mode used, p10/p90 values, recommended
   threshold, merge uplift observed, noise rate, classifier-validation result (X/20),
   OCR-noise caveat, re-tune trigger.
6. **Value consistency check (F11):** before commit, `grep -c "<chosen>" BACKLOG.md`
   and `grep -c "<chosen>" scripts/extract_cti_threats.py` must each return ≥1, and
   no reference to `0.15` in the dedup context remains in either file.
7. `extract_cti_threats.py:235` default updated and calibration comment added;
   single commit named `WP-138: calibrate threat dedup threshold from 0.15 to <chosen>`.

---

## Pre-mortem — twelve ways this could fail, and how the plan handles each

Conducted before committing. Each failure has a concrete mitigation baked into
the script, the tests, or the work order above. (This section subsumes and
extends an earlier generic "Risks and trade-offs" list; F2 covers tag-overlap
noise, F4 covers OCR noise, F3 covers drift, F7 covers greedy order-dependence,
and D6 in the Design decisions section covers the scale/model-binding risks.)

| # | Failure mode | Mitigation | Where it lives |
|---|------|----------|-----------|
| **F1** | `_auto_recommend` gives a noise-driven number when no gap exists | Refuse to recommend when `within.p90 >= between.p10`; return `None` + `no_gap_manual_required` status; CLI exits 2 in `--recommend` mode | D3 + unit test `test_auto_recommend[no-gap]` |
| **F2** | Tag-overlap is the wrong ground truth because it conflates attack stages | `--sample-for-review 20` subcommand; implementer hand-labels 20 pairs; ≥70% agreement is an acceptance gate; <70% halts WP-138 | CLI subcommand + acceptance criterion #4 |
| **F3** | Threshold drifts as new reports are ingested, nobody notices | `--verify` subcommand compares current default to fresh recommendation; exits 1 if drift >0.03 | CLI subcommand + integration test 3 |
| **F4** | OCR-garbage threats cluster artificially, biasing within.p90 downward | `--exclude-noise` flag; work order requires running with **and** without the flag, comparing recommendations, picking explicitly if they diverge | CLI flag + work-order step 4 |
| **F5** | Existing 364 threats stay under the old threshold, creating a mixed graph | Explicit decision in the plan: **ship default only** (option a). Add backlog item "WP-138b — apply calibrated threshold to existing Threat corpus via merge pass" as a follow-up | Work-order step 10 + new backlog item |
| **F6** | Existing queries assume 1 report → 1 threat and break when edges multiply | Pre-commit grep check: `grep -rn "IDENTIFIES" memory_service/ scripts/ tests/` looking for `COUNT(r)=1` or similar cardinality assumptions; flag and review hits | Work-order step 9 |
| **F7** | Greedy simulation order-sensitivity gives different merge counts on different orderings | Unit test `test_simulate_pair_rerun_order_invariance` asserts identical `merged_count` regardless of input order; simulation sorts internally by `created_at` | Unit test + simulation implementation |
| **F8** | Integration tests are too lax — a broken script would still pass | Tests parse the `--json` block and assert semantic invariants on corpus size, distribution shape, merge uplift, and status enum | Integration tests 1–3 |
| **F9** | Unit tests miss edge cases (empty, tagless, zero-norm, etc.) | Parametrised unit test with six hand-crafted cases | `test_classify_pairs` table |
| **F10** | `_print_histogram` reuse creates copy-paste drift | Deliberately decoupled: call `compute_histogram` for binning, write one local `_render_bars` function, accept the drift risk, comment-flag the parallel | D-section design choice + comment in source |
| **F11** | Calibration note in BACKLOG.md disagrees with the committed default | Value-consistency grep check in the work order; acceptance criterion #6 requires both files to reference the chosen value | Work-order step 12 + acceptance criterion #6 |
| **F12** | Subagents can't find the plan because it lives in `.claude/plans/` not `docs/plans/` | **Work-order step 0**: copy the plan to `docs/plans/wp138_threat_dedup_calibration.md` before any other work | Work-order step 0 |

---

## Work order (step-by-step for subagent-driven-development)

0. **Copy plan to the canonical location (F12 mitigation).** First action after plan
   approval, before any code:
   ```
   cp .claude/plans/async-booping-shell.md docs/plans/wp138_threat_dedup_calibration.md
   ```
   Rename/edit the copy's top note about plan-mode location. All subsequent subagent
   dispatches reference the `docs/plans/` path.

1. **Pre-flight verification (read-only).** Run:
   ```
   curl -s http://localhost:8000/health
   curl -s http://localhost:8000/knowledge/threats | jq 'length'
   python3 -c "from scripts.create_cross_framework_informs import compute_histogram, cosine_similarity_matrix; print('ok')"
   ```
   Expect: service ok, threat count ~364, imports succeed.

2. **Write `scripts/calibrate_threat_dedup.py`** (no tests yet). Structure:
   - Module docstring with usage block in the style of `scripts/dedup_cleanup.py:1-17`.
   - `from memory_service.config import Settings, get_driver`.
   - `_fetch_all_threats(session) -> list[dict]` — single Cypher, returns
     `{id, text, tags, created_at, embedding, report_id}`.
   - `_fetch_report_threats(session, report_ids) -> list[dict]` — Cypher over
     `(:ThreatReport)-[:IDENTIFIES]->(:Threat)`, filtered by `report_ids`.
   - `classify_pairs(threats, mode, dominant_tags=frozenset({"T1486","T1566","T1110"}))
     -> tuple[list[float], list[float]]` — **the pure unit-tested function.**
   - `_print_distance_histogram(values, label, bin_width, low, high)` — local wrapper
     around `compute_histogram`.
   - `_summarise(values) -> dict` — mean, median, p10, p50, p90, min, max, count.
   - `_auto_recommend(within, between) -> tuple[float, bool, str|None]`.
   - `_simulate_pair_rerun(threats_subset, threshold, baseline=0.15)
     -> dict` — returns canonical_count, merged_count, top_new_merges, baseline_merged_count.
   - `_ocr_noise_heuristic(text) -> bool`.
   - `main()` with argparse subcommand dispatcher and `--json` emitter.

3. **Manual smoke run — four modes compared (F2 + F4 mitigation).**
   ```
   python3 scripts/calibrate_threat_dedup.py --histogram
   python3 scripts/calibrate_threat_dedup.py --histogram --technique-mode dominant-three
   python3 scripts/calibrate_threat_dedup.py --histogram --exclude-noise
   python3 scripts/calibrate_threat_dedup.py --histogram --technique-mode dominant-three --exclude-noise
   ```
   Tabulate the four recommendations. Expected band: 0.18–0.32. Three checks:
   - (a) `tag-overlap` vs `dominant-three` agree within 0.03? If not, favour `dominant-three`.
   - (b) `--exclude-noise` vs unfiltered agree within 0.03? If not, the noise is biasing
     the calibration — pick the `--exclude-noise` value and record the delta in the
     calibration note.
   - (c) Any run returns `no_gap_manual_required`? If yes, inspect the histograms
     visually, pick a threshold by eye, and document the decision.

4. **Classifier validation — hand-label 20 pairs (F2 gated mitigation).**
   ```
   python3 scripts/calibrate_threat_dedup.py --sample-for-review 20 > /tmp/wp138_review.txt
   ```
   Open the output, read each pair's two threat texts, and label same-attack /
   different-attack. Compare your labels against the `tag-overlap` classifier's
   labels printed alongside. Compute agreement (correct_count / 20). **If <14/20,
   STOP.** The calibration is invalid; add a new backlog WP to escalate the approach
   and report back for direction. If ≥14/20, proceed.

5. **Pair-rerun simulation.**
   ```
   python3 scripts/calibrate_threat_dedup.py --pair-rerun --threshold <chosen>
   ```
   Inspect the top-10 new merges. If any pair looks like a false positive
   (semantically distinct techniques merged), lower the threshold by 0.02 and re-run.
   Accept when the top-10 are all true paraphrases.

6. **Write `tests/test_wp138_threat_dedup_calibration.py`:**
   - Unit tests per the parametrised table in §Test plan (six `classify_pairs` cases,
     three `_auto_recommend` cases, order-invariance test, OCR heuristic test).
   - Integration test 1: `--histogram --json` with semantic assertions.
   - Integration test 2: `--pair-rerun --threshold <chosen> --json` with uplift assertion.
   - Integration test 3: `--verify --json` with drift assertion.
   - All three integration tests marked `@pytest.mark.integration`.

7. **Run tests.**
   ```
   pytest tests/test_wp138_threat_dedup_calibration.py -v               # unit only
   pytest tests/test_wp138_threat_dedup_calibration.py -v -m integration
   ```
   Unit tests must all pass immediately. Integration tests require the live stack.

8. **Update `scripts/extract_cti_threats.py`:**
   - Line 235: change default from `0.15` to the chosen value.
   - Add two-line calibration comment above line 235 (see D6).
   - Update `help=` string to new default.
   - Update the usage example in the docstring at line 16.

9. **Audit existing IDENTIFIES cardinality assumptions (F6 mitigation).**
   ```
   grep -rn "IDENTIFIES" memory_service/ scripts/ tests/ | grep -E "COUNT|count|cardinality"
   ```
   Review each hit. If any query assumes one-report-per-threat, flag it in the commit
   message as a review item. For this spike, no code changes — just awareness.

10. **Verify `scripts/ingest_all_threat_reports.py` unchanged.** Confirm no
    `--dedup-threshold` is passed in the orchestrator subprocess command
    (lines 109–129). No edit — this is a *verification* step, not a change.

11. **Append calibration paragraph to `BACKLOG.md`** after line 1252 (the WP-108
    retrospective paragraph ending "highest-value fix."). Template (fill in actual
    values captured from the smoke run):
    ```
    **WP-138 calibration note (<date>):** Re-calibrated `--dedup-threshold` from
    0.15 to <chosen> based on self-similarity analysis of the 364-threat corpus.
    Method: pairwise cosine distances over `Threat.embedding`, classified
    within/between using ATT&CK tag overlap (cross-checked with dominant-three
    mode over T1486/T1566/T1110, both with and without --exclude-noise).
    Observed within.p90 = <x>, between.p10 = <y>; recommended threshold = <chosen>.
    Pair-rerun simulation on Verizon+ENISA predicted <M> merges at <chosen>
    vs <baseline> at 0.15. Classifier validated on 20 hand-labelled pairs:
    <X>/20 agreement. ~<N>% of the corpus flagged as likely OCR/PDF extraction
    noise — threshold chosen to be robust to this tail via p90/p10 rather than
    max/min. The existing 364 threats retain their original graph shape; a
    follow-up WP-138b will optionally apply a merge pass under the new default.
    Re-run `scripts/calibrate_threat_dedup.py --verify` after any new report
    ingestion or embedding-model change; drift >0.03 triggers re-calibration.
    ```

12. **Value-consistency check before commit (F11 mitigation).**
    ```
    grep -c "<chosen>" BACKLOG.md                  # expect ≥1
    grep -c "<chosen>" scripts/extract_cti_threats.py    # expect ≥1
    grep -n "0.15" scripts/extract_cti_threats.py         # expect no dedup-context hits
    ```
    All three checks must pass. The chosen value must appear in both files; no stray
    `0.15` dedup references should remain.

13. **Add follow-up backlog item WP-138b (F5 mitigation).** Append to BACKLOG.md
    prioritised table as a new row:
    ```
    | <next-order> | R2 | WP-138b | Apply calibrated dedup threshold to existing Threat corpus | L | L | 5.0 | WP-138 | One-off merge pass: run find_duplicates against all 364 existing Threats at the new default; merge pairs above threshold via existing WP-047 merge endpoint; preserves IDENTIFIES edge provenance. Unblocks uniform corpus state. |
    ```
    Score as 5.0 (High value / Low effort) since it's a pure cleanup using existing
    merge infrastructure.

14. **Run `/simplify` review** on the changed code per CLAUDE.md Definition of Done.

15. **Commit.** Single commit:
    ```
    WP-138: calibrate threat dedup threshold from 0.15 to <chosen>

    - new scripts/calibrate_threat_dedup.py (--histogram, --pair-rerun, --recommend,
      --verify, --sample-for-review, --exclude-noise)
    - new tests/test_wp138_threat_dedup_calibration.py (unit + 3 integration)
    - extract_cti_threats.py: default raised 0.15 -> <chosen>, model-binding comment
    - BACKLOG.md: WP-108 retrospective + calibration paragraph, new WP-138b row
    - ingest_all_threat_reports.py unchanged (inherits new default via argparse)
    ```

16. **Run `engineering:deploy-checklist`** per CLAUDE.md Definition of Done.

17. **Update `BACKLOG.md` WP-138 row** — move from "Currently In Progress" to
    "Completed" with retrospective note referencing the pre-mortem mitigations.

---

## Verification — how to test end-to-end

1. **Service health:** `curl -s http://localhost:8000/health` → `{"status":"ok"}`.
2. **Unit tests:** `pytest tests/test_wp138_threat_dedup_calibration.py -v` (unit only; skip `-m integration`) → all pass in <2s, including the six `test_classify_pairs` parametrised cases, `test_auto_recommend` (including the no-gap case), `test_simulate_pair_rerun_order_invariance`, and `test_ocr_noise_heuristic`.
3. **Histogram smoke test:**
   `python3 scripts/calibrate_threat_dedup.py --histogram` → prints within and between
   histograms with summary stats, gap analysis, and a recommended threshold in the
   range [0.18, 0.32]. Exit code 0.
4. **Dominant-three cross-check:**
   `python3 scripts/calibrate_threat_dedup.py --histogram --technique-mode dominant-three`
   → recommended threshold agrees with `tag-overlap` within 0.03, OR the calibration
   note explains the divergence.
5. **Pair-rerun simulation:**
   `python3 scripts/calibrate_threat_dedup.py --pair-rerun --threshold <chosen>`
   → prints merged_count ≥ 3× baseline_merged_count, top-10 merges visible, all
   manually confirmed as true paraphrases.
6. **Integration tests:**
   `pytest tests/test_wp138_threat_dedup_calibration.py -v -m integration` → all pass.
7. **Real ingestion dry-run (safety check):**
   `python3 scripts/ingest_all_threat_reports.py --dry-run` → completes without error,
   confirming the default bump does not break the orchestrator subprocess plumbing.
8. **Graph state unchanged:** `curl -s http://localhost:8000/knowledge/threats | jq 'length'`
   → still 364 (the spike does not mutate Memgraph).
9. **Search endpoint returns recalibrated behaviour (manual check):**
   `curl -s -X POST http://localhost:8000/knowledge/search/threats -d '{"query":"ransomware encrypted hospital files","limit":5}'`
   → expected: current behaviour (unchanged), but future ingestion via
   `extract_cti_threats.py` will merge the cross-report paraphrases now visible at
   distance 0.34.
