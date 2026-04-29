# WP-150: Defensive coercion of JSON-encoded list parameters in MCP tools

**Date:** 2026-04-29
**Status:** Ready for implementation
**Driver:** Live failure 2026-04-29 — Cowork MCP bridge passed `strand_ids='["strand-companion-protocols-systems"]'` (JSON-encoded string) to `memory_add`; FastMCP's auto-derived Pydantic validator rejected it.

---

## Summary

Add a Pydantic `BeforeValidator`-backed type alias `StrList` in `mcp_server/server.py` and apply it to every `list[str] | None = None` parameter across the FastMCP tool surface (~20 sites). The validator passes lists through unchanged, parses JSON-array strings via `json.loads`, wraps bare strings as single-element lists, and logs a warning whenever it has to coerce. Tool bodies are unchanged.

---

## Canonical symptom statement (user-facing bug report, 2026-04-29)

This is the user's framing of the same defect WP-150 addresses. Reproduced verbatim so the implementer and reviewer see the user-facing symptom alongside the fix.

> **MemFabric MCP — Array Parameter Serialisation Failure in Cowork**
> *Problem Report · 2026-04-29*
>
> **Symptom**
>
> Calls to `mcp__memory__memory_add`, `memory_update`, and `memory_reinforce` fail with a Pydantic v2 validation error whenever an array-typed parameter is supplied:
>
> ```
> Input should be a valid list [type=list_type,
>   input_value='["strand-companion-protocols-systems"]',
>   input_type=str]
> ```
>
> Affected parameters: `strand_ids`, `tags`, `co_recalled_ids`. All other parameters (strings, integers, nulls) work correctly.
>
> **Scope**
>
> Confirmed failing: Cowork companion sessions.
> Confirmed working: Claude Code sessions — same MCP bridge, same tool surface, same strand IDs thread without issue.
>
> **Root cause hypothesis**
>
> The MCP bridge (`memfabric.cjs`, Node stdio transport) receives array parameters correctly as JSON arrays from Claude Code's stdio framing. In the Cowork harness, the JSON-RPC layer appears to be serialising array values to their string representation before they reach the bridge — so `["strand-companion-protocols-systems"]` arrives as the *string* `'["strand-companion-protocols-systems"]'` rather than a Python list. Pydantic v2 refuses to coerce an arbitrary string into a list (by design, unlike v1), so validation fails hard.
>
> **Evidence**
>
> - Scalar params accepted in both harnesses.
> - Supplying no array params produces a successful write (lands in strand-inbox with a warning).
> - Error message shows input arriving typed as `str`, confirming pre-bridge stringification.
>
> **Impact**
>
> - Memories from Cowork cannot be strand-threaded at write time; accumulate in strand-inbox.
> - `co_recalled_ids` on reinforce fails — Hebbian edge strengthening blocked from Cowork.
> - Workaround: write without array params, re-thread from Claude Code.

---

## Approach

1. **Add a small coercion module.** Create `mcp_server/_coercion.py` with `_coerce_str_list` and the `StrList` Annotated alias. A separate module (rather than top-of-`server.py`) keeps `server.py` focused on tool definitions and gives a clean import surface for unit tests. Module-private (`_coercion.py`) signals "internal helper, not part of the tool API".
2. **Future-proofing.** The current need is `list[str]` only, so the alias is concretely typed `list[str] | None`. To leave the door open for `list[int]` etc. without committing to it now, also expose a generic factory `make_list_coercer(item_type: type)` that returns a parametrised `BeforeValidator`. We do NOT use the factory in WP-150 — we just leave it available so a future non-string list parameter can opt in without redesign. Documented in a docstring; not exported beyond the module.
3. **Wire into server.py.** Replace `list[str] | None = None` with `StrList = None` at every site. Add `from mcp_server._coercion import StrList` near the top of the file. No tool body changes.
4. **Validate FastMCP behaviour.** Already verified locally on FastMCP 3.2.4: `Annotated[..., BeforeValidator(...)]` is honoured (string `'["a","b"]'` → `["a","b"]`; real list passes through; bare string `"bare"` → `["bare"]`). The published JSON schema still presents the parameter as `array | null`, so MCP discovery output is unchanged for compliant clients.
5. **Logging hygiene.** The warning includes the parameter name (via the validator field info if available, otherwise just the raw value with truncation to 200 chars to avoid leaking large payloads into logs). Logged once per coercion; no rate limiting needed at this scale.

### Sites to update (~20)

| Tool | Parameters |
|------|-----------|
| `memory_add` | `strand_ids`, `tags`, `cause_ids`, `effect_ids`, `person_ids`, `control_ids`, `doc_ids` |
| `memory_search` | `tags`, `agent_ids`, `person_ids` |
| `memory_update` | `tags`, `person_ids`, `strand_ids`, `control_ids`, `doc_ids` |
| `memory_reinforce` | `co_recalled_ids` |
| `task_add` | `memory_ids` |

Total: 17 sites. (The BACKLOG estimate "~20" included `agent_ids` in `memory_search`; exact count = 17.)

---

## Affected Files

| File | Change |
|------|--------|
| `mcp_server/_coercion.py` | **New.** `_coerce_str_list`, `StrList` alias, `make_list_coercer` factory (unused, future-proofing). Module-level logger. |
| `mcp_server/server.py` | Import `StrList` from `_coercion`; replace 17 `list[str] \| None` annotations with `StrList`. No body changes. |
| `tests/test_wp150_mcp_list_coercion.py` | **New.** Unit tests for `_coerce_str_list` + integration tests against live MCP HTTP transport. |

---

## Cypher Patterns

None. WP-150 is purely an input-validation layer; no schema or query changes.

---

## Test Plan

Per CLAUDE.md, this section is the `engineering:testing-strategy` output and is mandatory before any code is written.

### Unit tests — `tests/test_wp150_mcp_list_coercion.py` (no live stack)

| ID | Test | Verifies |
|----|------|----------|
| U-1 | `test_coerce_none_passthrough` | `_coerce_str_list(None) is None` |
| U-2 | `test_coerce_real_list_passthrough` | `_coerce_str_list(["a","b"]) == ["a","b"]` (no warning logged) |
| U-3 | `test_coerce_json_array_string` | `_coerce_str_list('["a","b"]') == ["a","b"]` (warning logged) |
| U-4 | `test_coerce_json_array_string_with_whitespace` | `_coerce_str_list('  ["a"]  ') == ["a"]` |
| U-5 | `test_coerce_bare_string_to_single_element` | `_coerce_str_list("hello") == ["hello"]` (warning logged) |
| U-6 | `test_coerce_malformed_json_returns_original` | `_coerce_str_list('[broken')` returns original string so Pydantic's strict validator emits the canonical error |
| U-7 | `test_coerce_json_object_string_returns_original` | `_coerce_str_list('{"k":"v"}')` is not a list → returns original |
| U-8 | `test_coerce_non_string_non_list_passthrough` | `_coerce_str_list(42)` returns `42` unchanged → Pydantic rejects with the right message |
| U-9 | `test_strlist_alias_accepts_json_string_via_pydantic` | Use `pydantic.TypeAdapter(StrList).validate_python('["x"]')`; result is `["x"]` |
| U-10 | `test_strlist_alias_accepts_real_list` | `TypeAdapter(StrList).validate_python(["x"])` is `["x"]` |
| U-11 | `test_strlist_alias_rejects_non_string_items` | `TypeAdapter(StrList).validate_python([1,2])` raises `ValidationError` (Pydantic still enforces inner type) |
| U-12 | `test_warning_logged_only_on_coercion` | With `caplog`: list input emits 0 warnings; string input emits 1 warning at WARNING level |
| U-13 | `test_make_list_coercer_factory_int` | Sanity-check the future-proofing helper: `make_list_coercer(int)` coerces `'[1,2]'` to `[1,2]` (factory unused in production but must work if reached for) |

### Integration tests — `tests/test_wp150_mcp_list_coercion.py` (`@pytest.mark.integration`, live stack required)

Stack prerequisites: Memgraph + FastAPI service running at `http://localhost:8000` with `/mcp` mounted (same setup as WP-105 integration tests). Reuses the `_mcp_call`, `_get_api_key`, and `test_driver` patterns from `tests/test_wp105_mcp_http.py`.

| ID | Test | Verifies | Cleanup |
|----|------|----------|---------|
| I-1 | `test_i1_memory_add_accepts_json_string_strand_ids` | POST `tools/call memory_add` with `strand_ids='["strand-inbox"]'` (JSON string). Response 200, memory created, `strand_ids: ["strand-inbox"]` in result. | `cleanup_nodes(test_driver, memory_id)` |
| I-2 | `test_i2_memory_add_real_list_strand_ids_unchanged` | Same call with `strand_ids=["strand-inbox"]` (real list). Memory created, identical result shape. Regression guard for compliant clients. | `cleanup_nodes` |
| I-3 | `test_i3_memory_add_json_string_threading_verified` | After I-1, call `memory_search` for the fact and confirm the returned memory's `strand_ids` (or its `IN_STRAND` edge from the graph via `test_driver`) matches `["strand-inbox"]`. This is the acceptance criterion #2. | as I-1 |
| I-4 | `test_i4_memory_add_bare_string_strand_ids` | Call with `strand_ids="strand-inbox"` (bare string, not JSON). Coerced to `["strand-inbox"]`; memory threaded correctly. | `cleanup_nodes` |
| I-5 | `test_i5_memory_search_json_string_tags` | `memory_search` with `tags='["test"]'` returns 200 (no validation error). Confirms coercion works on the search side too. | none |
| I-6 | `test_i6_memory_add_malformed_json_returns_validation_error` | Call with `strand_ids='[broken'`. Response is the canonical FastMCP/Pydantic validation error, NOT a 500 — proves we do not swallow real client bugs. | none |
| I-7 | `test_i7_memory_update_json_string_strand_ids` | Create a memory threaded to one strand; call `memory_update` with `strand_ids='["strand-test"]'` (JSON-encoded). Assert the memory's strand membership is replaced — verify via `memory_search` (returned `strand_ids` matches) or via `test_driver` direct Cypher on the `IN_STRAND` edge. Maps directly to the user-reported `memory_update` failure. | `cleanup_nodes(test_driver, memory_id)` |
| I-8 | `test_i8_memory_reinforce_json_string_co_recalled_ids` | Create two memories (A and B); call `memory_reinforce` on A with `co_recalled_ids='["<uuid-of-B>"]'` (JSON-encoded). Assert the call succeeds (no validation error) and the Hebbian edge fires — query the `RELATED_TO` edge between A and B via `test_driver` and confirm `activation_count` incremented and `last_activated_at` updated. Maps directly to the user-reported `memory_reinforce` failure. | cleanup both memories |
| I-9 | `test_i9_task_add_json_string_memory_ids` | `task_add` with `memory_ids='["uuid-1","uuid-2"]'` is accepted (any DB-side errors about missing memories are separate; we check the validation layer only). | delete the created task |

Coverage note: integration tests now cover all three tools named in the 2026-04-29 user bug report — `memory_add` (I-1..I-4, I-6), `memory_update` (I-7), and `memory_reinforce` (I-8) — each exercised with a JSON-string-encoded list parameter.

### Acceptance Criteria (from BACKLOG, mapped)

1. **AC-1 (BACKLOG #1):** `_coerce_str_list` accepts `None`, list, JSON-array string, bare string; rejects malformed JSON cleanly. → **U-1..U-8**
2. **AC-2 (BACKLOG #2):** Live-stack `memory_add` with JSON-encoded `strand_ids` creates a correctly threaded memory; verified via follow-up read. → **I-1, I-3**
3. **AC-3 (BACKLOG #3):** Real-list callers unchanged. → **I-2**
4. **AC-4 (BACKLOG #4):** Warning fires on coercion, silent on real list. → **U-12** (unit) + manual log inspection during I-1.
5. **AC-5 (BACKLOG #5):** `/simplify` clean, `engineering:deploy-checklist` green. → done at WP closure, not in this plan.

### Test execution order

1. Run all U-* unit tests first — fast, no infra. Must pass before any integration test is run.
2. Bring up live stack (`docker compose up -d memgraph` + `uvicorn memory_service.main:app`).
3. Run integration tests with `pytest -m integration tests/test_wp150_mcp_list_coercion.py`.
4. Run full suite once to confirm no regressions in WP-105 or WP-033 MCP tests.

---

## Risks / Edge Cases

| Risk | Mitigation |
|------|-----------|
| Coercion masks real client bugs | Warning log on every coercion; malformed JSON falls through to Pydantic's real error (U-6, I-6). |
| Bare-string-to-list coercion is too eager — could swallow a typo where the user passed `"strand_ids='strand-inbox'"` thinking it was a typed list | Explicit choice: this is the behaviour the BACKLOG entry asks for, and the WARNING log makes the misbehaviour visible. Documented in the helper docstring. |
| Future `list[int]` parameter added without thinking | `make_list_coercer` factory exists but unused; reviewer must consciously opt in for non-string lists. Alternative considered: refuse to expose a factory until needed. Rejected because the cost is one unused function and the benefit is a clear extension point. |
| FastMCP version upgrade silently changes how `Annotated[..., BeforeValidator]` is processed | Verified empirically against installed FastMCP 3.2.4 (see notes below). U-9..U-11 act as canaries — if a future upgrade breaks the contract, those tests fail loudly. |
| Logging volume from a misbehaving client | Coercion happens once per tool call; even at high traffic this is bounded by request volume. No rate limiting added; revisit only if logs become noisy. |
| Memory dedup interaction in I-1 | `memory_add` checks for duplicates by fact text. Use a unique fact like `"WP-150 integration test {uuid}"` per test run to avoid hitting the dedup path and getting `deduplicated: true` (which would still pass the schema check but make the strand-threading assertion ambiguous). |

---

## Reuse / Patterns Identified

- **Test scaffolding:** `tests/test_wp105_mcp_http.py::_mcp_call`, `::_get_api_key`, the `test_driver` fixture, and `tests/conftest.py::cleanup_nodes` are directly reused. No new fixtures needed.
- **Integration mark:** `@pytest.mark.integration` (see CLAUDE.md "Memgraph Cypher gotchas" — new integration tests must be marked explicitly).
- **No existing JSON-coercion helpers in repo.** Searched `mcp_server/`, `memory_service/`, `memory_client/` — no precedent. The new helper is the first of its kind.
- **Module placement decision:** `mcp_server/_coercion.py` (private). Alternative considered: top of `server.py`. Rejected because (a) `server.py` is already 900 lines and largely tool definitions, (b) a separate file makes the helper directly importable in unit tests without dragging the whole server module (and its driver/embedding side effects) into the test process.

---

## FastMCP Compatibility Note

Verified manually against the installed FastMCP 3.2.4:

```python
from typing import Annotated
from pydantic import BeforeValidator
from fastmcp import FastMCP

def coerce(v):
    if isinstance(v, str): ...

StrList = Annotated[list[str] | None, BeforeValidator(coerce)]

@mcp.tool
def t(xs: StrList = None) -> dict: ...

# tool.run({"xs": '["a","b"]'}) -> structured_content={"xs": ["a","b"]}  ✓
# tool.run({"xs": ["a","b"]})    -> structured_content={"xs": ["a","b"]}  ✓
# tool.run({"xs": "bare"})       -> structured_content={"xs": ["bare"]}   ✓
```

The published JSON schema for the parameter is unchanged (`{"anyOf": [{"items": {"type": "string"}, "type": "array"}, {"type": "null"}]}`), meaning MCP `tools/list` discovery output is identical for compliant clients — they see exactly what they see today.

---

## Rollback Path

Single-file rollback. If the coercion proves problematic in production:

1. `git revert <commit>` reverts both `mcp_server/_coercion.py` (deletion) and the 17 annotation changes in `server.py`.
2. No data migration, no schema change, no operational state — the change is purely declarative at the input boundary.
3. The `engineering-implementer` should ensure the commit is atomic (single commit, all sites + new module + tests) so the revert is one operation.

Back-out preserved: the implementer creates the change in a single commit on `master`; the revert commit is the back-out path. No data is destroyed.

---

## Out of Scope

- Filing the upstream Anthropic bug report about Cowork's MCP bridge double-encoding. Tracked as a separate side action in the BACKLOG entry, not blocking this WP.
- Coercing other shapes (e.g. JSON object strings, numeric strings to int). Only `list[str] | None` parameters are in scope.
- HTTP-layer (REST) endpoints in `memory_service/main.py`. Those use `Body(...)` with explicit Pydantic models; no observed double-encoding issue and out of WP-150 scope.

---

## Definition of Done (from CLAUDE.md)

1. ✅ Test plan above is the `engineering:testing-strategy` output, attached to this plan file.
2. Unit tests (U-1..U-13) written and passing under `pytest`.
3. Integration tests (I-1..I-9) written and run against the live stack.
4. AC-2 verified manually via a sample MCP HTTP call from the dev shell.
5. `/simplify` run on the diff; findings actioned or deferred.
6. `engineering:deploy-checklist` green.
7. BACKLOG.md: WP-150 moved from "Currently In Progress" to Completed; retrospective note added.
8. Git commit: `WP-150: Defensive coercion of JSON-encoded list parameters in MCP tools` (created from Git Bash on Windows per CLAUDE.md).
