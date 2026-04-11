# WP-SEC-R Group B: Destructive Git + Supply-Chain Ask-Tier Hardening

**Date:** 2026-04-11
**Status:** Ready for implementation
**WPs:** WP-SEC-R10, WP-SEC-R12
**Target file:** `/home/oliver/projects/graph-memory-fabric/.claude/settings.json`

---

## Summary

Add 11 destructive git operation patterns (WP-SEC-R10) and 11 supply-chain install command
patterns (WP-SEC-R12) to the `permissions.ask` array in `.claude/settings.json`. Both WPs
modify the same array and must be applied in a single Edit call to avoid a race condition
between two edits to the same file region.

---

## Context and Rationale

### Phase 0 probe results (already confirmed — do not re-probe)

- **P0.2 CONFIRMED:** Evaluation order is deny -> ask -> allow, first match wins. An entry in
  `ask` will trigger a prompt even when `Bash(git *)` appears in `allow`. The wildcard allow
  does not override a more-specific ask rule.
- **P0.3 CONFIRMED:** Pipe characters in `Bash(...)` patterns do not work — patterns only
  match on prefix. `Bash(curl * | sh*)` will not match a piped command. Curl/wget are already
  gated by existing ask rules; pipe-to-shell is a documented known gap.
- **P0.5 CONFIRMED:** No force-push or reset --hard in project or bash history. Low friction
  to add these; no daily-use disruption expected.

### Current state of settings.json (as-read 2026-04-11)

The file is 139 lines. Key array sizes at time of reading:

| Array  | Entry count |
|--------|-------------|
| deny   | 11          |
| ask    | 33          |
| allow  | 25          |

Note: the background brief described 14 deny entries and 15 ask entries, but the live file
has 11 deny and 33 ask entries (the file has already received prior hardening additions).
The implementation steps below are based on the live file content.

Existing ask entries relevant to this sprint:
- Line 44: `"Bash(sudo*)"`
- Line 45: `"Bash(pip install *)"`
- Line 46: `"Bash(curl http*)"`
- Line 47: `"Bash(curl https*)"`
- Line 48: `"Bash(docker compose down*)"`
- Line 49: `"Bash(docker volume *)"`

Existing allow entry: Line 74: `"Bash(git *)"` — wildcard allow for all git commands.
P0.2 confirms ask-tier entries override this for matching prefixes.

Allow entries that must not be disturbed (service health checks):
- Line 91: `"Bash(curl http://127.0.0.1*)"`
- Line 92: `"Bash(curl http://localhost*)"`

---

## Scope

### WP-SEC-R10 — Destructive git operations to ask-tier

Rationale: prompt injection could direct the assistant to destroy work. These operations are
infrequent in legitimate use. P0.5 confirms none appear in Oliver's history.

Entries to add:
```
"Bash(git push --force*)",
"Bash(git push --force-with-lease*)",
"Bash(git push -f*)",
"Bash(git reset --hard*)",
"Bash(git clean -f*)",
"Bash(git branch -D *)",
"Bash(git branch -d *)",
"Bash(git checkout .*)",
"Bash(git checkout -- *)",
"Bash(git restore .*)",
"Bash(git restore --source*)"
```

### WP-SEC-R12 — Supply-chain install commands to ask-tier

Rationale: arbitrary package installs are a supply-chain attack vector. `pip install *` is
already in ask; this WP extends coverage to other package managers. Curl-pipe-to-shell is not
achievable via pattern matching (P0.3 confirmed) — documented as a known gap.

Entries to add:
```
"Bash(wget*)",
"Bash(uv pip install*)",
"Bash(uv add*)",
"Bash(npm install*)",
"Bash(npm i *)",
"Bash(yarn add*)",
"Bash(pnpm add*)",
"Bash(cargo install*)",
"Bash(go install*)",
"Bash(gem install*)",
"Bash(brew install*)"
```

Known gap: pipe-to-shell patterns (`curl ... | sh`, `wget ... | bash`) cannot be gated via
prefix matching. Mitigation: curl and wget are individually gated in ask-tier; a human
approval step is required before either tool runs, which breaks the pipe-to-shell attack
chain at the first command.

---

## Affected Files

| File | Change |
|------|--------|
| `.claude/settings.json` | Add 22 entries to `permissions.ask` array (R10: 11, R12: 11) |
| `tests/test_wp_sec_r_settings.py` | Create — 8 structural tests (no live service required) |

---

## Implementation Approach

### Step 1 — Read the file before editing

The implementer MUST read `.claude/settings.json` immediately before editing to confirm the
current closing region of the ask array. Do not rely on line numbers from this plan document
as other edits may have occurred. The read confirms the exact string to replace.

### Step 2 — Single Edit call for both WPs

Both WP-SEC-R10 and WP-SEC-R12 add entries to the same `permissions.ask` array. Apply all
22 entries in ONE Edit call. Do not make two separate edits to the same array — the second
edit would need to re-read the result of the first, and the old_string from this plan would
no longer match.

The edit replaces the tail of the ask array (the last existing entry plus closing bracket)
with the last existing entry, the R10 block, the R12 block, and the closing bracket.

Concretely, the old_string to match is the current last two lines of the ask array:

```json
      "Bash(docker volume *)"
    ],
```

The new_string inserts all new entries before the closing bracket, R10 group first then R12
group, each group separated by a blank line for visual grouping:

```json
      "Bash(docker volume *)",

      "Bash(git push --force*)",
      "Bash(git push --force-with-lease*)",
      "Bash(git push -f*)",
      "Bash(git reset --hard*)",
      "Bash(git clean -f*)",
      "Bash(git branch -D *)",
      "Bash(git branch -d *)",
      "Bash(git checkout .*)",
      "Bash(git checkout -- *)",
      "Bash(git restore .*)",
      "Bash(git restore --source*)",

      "Bash(wget*)",
      "Bash(uv pip install*)",
      "Bash(uv add*)",
      "Bash(npm install*)",
      "Bash(npm i *)",
      "Bash(yarn add*)",
      "Bash(pnpm add*)",
      "Bash(cargo install*)",
      "Bash(go install*)",
      "Bash(gem install*)",
      "Bash(brew install*)"
    ],
```

### Step 3 — Validate JSON

After the edit, run:

```
jq empty /home/oliver/projects/graph-memory-fabric/.claude/settings.json
```

Exit code 0 = valid JSON. Any non-zero exit means the edit introduced a syntax error; revert
and retry.

### Step 4 — Create test file

Create `tests/test_wp_sec_r_settings.py` containing the 8 structural tests described in the
Test Plan section below.

### Step 5 — Run tests

```
pytest tests/test_wp_sec_r_settings.py -v
```

All 8 tests must pass before the WP is considered complete.

### Important: ask-tier on settings.json itself

`Edit(/home/oliver/projects/graph-memory-fabric/.claude/settings.json)` is itself in the
ask-tier (line 23 of the ask array). The Edit call in Step 2 will trigger a user approval
prompt. This is expected and correct — approve it.

---

## Cypher Patterns

Not applicable. This WP contains no database changes.

---

## Test Plan

### Overview

`settings.json` is configuration, not executable code. All tests are structural — they load
the JSON file and assert on its contents. No live service, no Memgraph, no FastAPI required.

**Test file:** `tests/test_wp_sec_r_settings.py`

### Unit Tests (no live stack required)

All 8 tests below belong in `tests/test_wp_sec_r_settings.py`. Use a module-level fixture
that loads the file once:

```python
import json, pathlib, pytest

SETTINGS_PATH = pathlib.Path(__file__).parent.parent / ".claude" / "settings.json"

@pytest.fixture(scope="module")
def settings():
    with open(SETTINGS_PATH) as f:
        return json.load(f)
```

| Test name | What it asserts |
|-----------|----------------|
| `test_settings_json_is_valid_json` | `json.load(SETTINGS_PATH.open())` raises no exception |
| `test_r10_destructive_git_entries_present` | Each of the 11 R10 entries is in `settings["permissions"]["ask"]` |
| `test_r12_supply_chain_entries_present` | Each of the 11 R12 entries is in `settings["permissions"]["ask"]` |
| `test_existing_ask_entries_unchanged` | All 33 original ask entries are present (additions only, no removals) |
| `test_existing_deny_entries_unchanged` | All 11 deny entries are present and unchanged |
| `test_existing_allow_entries_unchanged` | All 25 allow entries are present and unchanged |
| `test_ask_array_has_no_duplicates` | `len(ask) == len(set(ask))` |
| `test_curl_localhost_allow_still_present` | `"Bash(curl http://127.0.0.1*)"` and `"Bash(curl http://localhost*)"` are in allow |

The `test_existing_ask_entries_unchanged` test must enumerate all 33 entries that were
present before this WP ran, verifying none were removed or reordered. The current 33 entries
are the exact list visible at lines 17-49 of the file as-read on 2026-04-11.

### Integration Tests

None required. This WP has no service-layer changes.

### Acceptance Criteria

1. `jq empty .claude/settings.json` exits 0 (valid JSON).
2. All 8 structural tests in `tests/test_wp_sec_r_settings.py` pass under `pytest`.
3. Full `pytest` suite remains green (no regressions).
4. Manual smoke (post-merge, not automated): in the next live session, attempt
   `git reset --hard HEAD~1` — the Claude Code harness should present an ask-tier approval
   prompt before running the command. Record outcome as post-merge verification.

---

## Risks and Open Questions

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Pipe-to-shell (`curl ... \| sh`) cannot be gated by prefix pattern (P0.3) | Low | curl and wget individually gated; human must approve each tool before pipe executes |
| Edit call triggers ask-tier prompt for settings.json itself | Expected / not a risk | Approve the prompt; this is the correct behaviour |
| Line numbers in this plan may drift if other edits occur first | Low | Step 1 requires a fresh Read immediately before editing; use content matching, not line numbers |
| Two-WP single-Edit requirement | Medium | Implementer must not split into two Edit calls on the same array; the old_string must uniquely match the current file tail |

### Known gap (documented)

Curl-pipe-to-shell attack patterns cannot be blocked via `Bash(...)` prefix matching in
Claude Code settings. The existing mitigations (curl and wget individually in ask-tier) mean
a human approval step is required before either download tool runs, which breaks the attack
chain before the pipe executes. No further action planned for this gap in this sprint.
