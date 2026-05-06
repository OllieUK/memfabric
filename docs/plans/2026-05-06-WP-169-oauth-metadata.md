# WP-169: OAuth protected-resource metadata for MCP discovery

**Date:** 2026-05-06
**Status:** Ready for implementation
**Driver:** Live failure 2026-05-06 — Claude Code MCP TS client (per the 2025-06-18 MCP Authorization spec) probes RFC 9728 OAuth metadata before sending `initialize`. memfabric returns FastAPI's default `404 {"detail":"Not Found"}` at `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource`, and `401 {"detail":"Invalid or missing API key"}` at `/mcp/.well-known/oauth-protected-resource` (because `BearerTokenMiddleware` wraps the entire `/mcp` sub-app). The SDK then tries to parse the bodies as RFC 6749 OAuth errors, hits `ZodError: path:["error"] expected: string, received: undefined` because `detail` is not `error`, and reports `SDK auth failed: HTTP 404`. Net effect: `mcp__memory__*` tools never register in fresh Claude Code sessions, even though bearer auth and `POST /mcp/` initialize work fine when invoked manually.

---

## Context

`memory_service/main.py` exposes the FastMCP server as a Starlette ASGI sub-app mounted at `/mcp` (lines 80–85, 126). The sub-app is wrapped in `BearerTokenMiddleware` (`memory_service/mcp_auth.py`) which today validates `Authorization: Bearer ...` / `X-Api-Key` for every request that reaches `/mcp`, with no allow-list. The top-level FastAPI `app` carries `dependencies=[Depends(verify_api_key)]` (line 123); `verify_api_key` (`memory_service/auth.py`) has its own `_OPEN_PATHS` allow-list — currently `frozenset({"/health"})`.

ADR-003 (auth wiring at the ASGI mount boundary) is intentional and out of scope. This WP is a small, targeted carve-out so two specific discovery paths return the right RFC 9728 JSON without authentication, and nothing else changes.

Verified against the running service:
- `GET /.well-known/oauth-protected-resource` → 404 (FastAPI default, `{"detail":"Not Found"}`)
- `GET /.well-known/oauth-authorization-server` → 404
- `GET /mcp/.well-known/oauth-protected-resource` → 401 (caught by `BearerTokenMiddleware` before reaching the FastMCP app, which would also 404)
- `POST /mcp/` with bearer + `Accept: application/json, text/event-stream` → 200 SSE `initialize`

---

## Goal

Serve a real RFC 9728 protected-resource metadata document at the discovery paths the MCP TS client probes, so it stops misinterpreting our 404/401 responses as broken OAuth errors and proceeds to bearer-token initialize. Concretely:

1. `GET /.well-known/oauth-protected-resource/mcp` → 200 + valid JSON (no auth required)
2. `GET /.well-known/oauth-protected-resource` → 200 + same JSON (no auth required)
3. `GET /mcp/.well-known/oauth-protected-resource` → 200 + same JSON (no auth required, served from outside the `BearerTokenMiddleware`)
4. Bearer-token enforcement on every other `/mcp/*` and `/memory/*` path is unchanged.
5. `claude mcp list` shows `memory: ✓ Connected` after a fresh service restart.

---

## Approach

### Chosen option: serve real RFC 9728 metadata, not just a clean 404

Three options were considered. The chosen approach is option B.

| Option | Sketch | Verdict |
|--------|--------|---------|
| A | Return clean 404s with a body shaped like `{"error":"not_found"}` so the SDK's RFC 6749 parser doesn't ZodError. | Rejected. Still leaves the SDK in a "broken AS metadata" code path; relies on undocumented SDK fallback behaviour to recover. |
| **B** | **Serve real RFC 9728 protected-resource metadata with `authorization_servers: []` to signal "no AS — use bearer directly".** | **Chosen.** Tells the SDK exactly what we are: a protected resource that takes a static bearer token. Closes the bug at the spec layer. |
| C | Spin up an actual OAuth authorization server endpoint with token exchange. | Rejected. Out of scope — the user explicitly asked to keep `.mcp.json`'s static-bearer mechanism. |

### Implementation steps

1. **Add config setting `public_base_url`.** New `pydantic-settings` field on `Settings` in `memory_service/config.py`, default `"http://localhost:8000"`, env var `PUBLIC_BASE_URL`. Used to compute the `resource` URL in the RFC 9728 document. Documented in `.env.example` with the prod value (`https://memfabric.carr-it.net`) called out in a comment. **No hard-coded hosts** anywhere.

2. **Add `_DISCOVERY_PATH_SUFFIXES` allow-list to `BearerTokenMiddleware`.** Module-level constant: `frozenset({"/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server"})`. Inside `BearerTokenMiddleware.__call__`, after the `scope["type"]` and `settings.api_keys` short-circuits, check if `scope["path"]` (which, for the mounted sub-app, is the path **relative to the mount** — verified via inspection; e.g. `/.well-known/oauth-protected-resource` for a request to `/mcp/.well-known/oauth-protected-resource`) ends in any of the allow-listed suffixes. If yes, pass through to the inner app without bearer validation. Tight matching on path *suffix* (not substring) prevents `/mcp/x/.well-known/oauth-protected-resource-evil` from accidentally matching.

   - Why suffix check rather than exact equality on `scope["path"]`? Starlette's mount rewrites `scope["path"]` to the path beneath the mount (so for the FastMCP sub-app the path will be `/.well-known/oauth-protected-resource`, not `/mcp/.well-known/oauth-protected-resource`). Suffix is a small concession to robustness if a future mount layout changes.
   - Why a frozenset of *suffixes* rather than regex? Cheap, explicit, and trivially auditable in `/simplify` review.

3. **Register the discovery routes on a fresh sub-router that bypasses `verify_api_key`.** The cleanest carve-out is to define a small `APIRouter` with no dependencies and `app.include_router(discovery_router)` *without* propagating `app.dependencies`. FastAPI's behaviour: dependencies declared on the `FastAPI(...)` instance via `dependencies=[...]` apply to **every endpoint** registered against that app, regardless of whether they came in through `include_router(...)` or direct `@app.get`. To bypass them, the most surgical option is to extend `_OPEN_PATHS` in `memory_service/auth.py` (which `verify_api_key` already consults) — that is a one-line change to the existing allow-list mechanism, exactly the same pattern the WP itself is using for `BearerTokenMiddleware`.

   **Decision: extend `_OPEN_PATHS` in `verify_api_key`.** Reasoning:
   - Smallest surface change (one constant edit in one existing file).
   - Same pattern is already used for `/health`. Reviewers find the mechanism familiar.
   - Preserves option (b) and (c) from the brief without their downsides: doesn't move the dependency off `app` (b would need to retag every router) and doesn't introduce a second dependency-free app (c would split the routing tree).
   - The discovery paths are explicit and intentionally public, like `/health`. Putting them in the same allow-list documents that intent in one place.

4. **Define the JSON document.** Schema (RFC 9728 §3, Protected Resource Metadata):
   ```json
   {
     "resource": "{public_base_url}/mcp/",
     "authorization_servers": [],
     "bearer_methods_supported": ["header"],
     "resource_documentation": "https://github.com/ollieuk/graph-memory-fabric"
   }
   ```
   - `resource`: URL of the protected resource (the MCP endpoint). Must end in `/mcp/` to match what the SDK probed.
   - `authorization_servers: []`: signals "no separate AS — the resource server itself accepts the bearer." This is the magic value that tells RFC 9728 clients to stop probing for `/.well-known/oauth-authorization-server` and use the static bearer.
   - `bearer_methods_supported: ["header"]`: matches `Authorization: Bearer ...` (no `body` or `query`).
   - `resource_documentation`: optional but cheap. Points at the public repo for any human investigating the metadata. The exact URL is a string config value (`resource_documentation_url` setting, default `"https://github.com/ollieuk/graph-memory-fabric"`, env override possible) so it can be retargeted without a code change. **Open question O-1 below covers whether to make this a setting or a hardcoded literal — recommendation is hardcoded literal since it points at a fixed repo and config bloat is real.**

5. **Three routes, one handler.** Define one async handler `_oauth_protected_resource_metadata()` that returns the dict. Register it three times via the sub-router:
   - `/.well-known/oauth-protected-resource/mcp` — RFC 9728 path-suffix-disambiguated form (when there are multiple resources, the suffix names the resource; here `/mcp` matches our `resource` URL).
   - `/.well-known/oauth-protected-resource` — root form. Some SDK versions probe one, some the other; covering both is cheap.
   - `/mcp/.well-known/oauth-protected-resource` — required because the SDK probes the path **under** the resource. Bypasses both `verify_api_key` (via `_OPEN_PATHS`) **and** `BearerTokenMiddleware` (via the suffix allow-list in step 2).

   The third path is the one that crosses both auth boundaries. Step 2 carves out `BearerTokenMiddleware`; the route is registered on the top-level FastAPI app (not on the FastMCP sub-app), so the middleware's pass-through reaches Starlette's mount router which then... wait. Subtle: routes registered on `app` are matched **before** `/mcp` is mounted on `app`, but only because Starlette's mount routing is path-based and the most specific match wins. **Verification step (R-1):** during implementation, confirm via `httpx.get("/mcp/.well-known/oauth-protected-resource")` that the top-level app route (`/mcp/.well-known/oauth-protected-resource`) wins over the `/mcp` mount. If FastAPI/Starlette routes the request to the mount instead, the fallback is to register the discovery route on the FastMCP sub-app *itself*, but that means using FastMCP's route-registration API (or an additional middleware shim) — slightly more code but still small. Plan documents both paths; implementer chooses based on the empirical test in step (5) of implementation.

6. **Do not serve `/.well-known/oauth-authorization-server`.** RFC 9728 §3 states that when `authorization_servers` is empty (or absent), the client MUST NOT probe an authorization server. We do not control SDK behaviour, but spec-compliant clients (the 2025-06-18 spec the SDK targets) should accept the empty array. If post-implementation testing shows the SDK still probes `/.well-known/oauth-authorization-server`, file a follow-up WP to add a stub AS metadata document (or a clean `404 {"error":"not_found"}` body) — but do not pre-emptively add it now. Tracking this as **Open question O-2 below.**

### Rejected alternatives

- **Move `verify_api_key` from `app.dependencies` to per-router dependencies.** Touches every router file, large blast radius, no real benefit over extending `_OPEN_PATHS`.
- **Register discovery routes on a sibling FastAPI sub-app mounted alongside `/mcp`.** Adds a second ASGI app to manage; gain is zero.
- **Make `BearerTokenMiddleware` smarter via regex / glob.** Frozen-set suffix match is simpler and tighter.
- **Serve the metadata from inside the FastMCP sub-app via a FastMCP route.** FastMCP is a JSON-RPC tool server, not a generic HTTP route registrar; the route would be awkward and the auth carve-out would have to happen anyway. The carve-out IS the work.

---

## Affected Files

| File | Change |
|------|--------|
| `memory_service/mcp_auth.py` | Add module-level `_DISCOVERY_PATH_SUFFIXES = frozenset({...})`. In `BearerTokenMiddleware.__call__`, after the `scope["type"]` check and before the `settings.api_keys` check (so this works regardless of whether auth is enabled), add a path-suffix guard that passes through. |
| `memory_service/auth.py` | Extend `_OPEN_PATHS` to include `/.well-known/oauth-protected-resource`, `/.well-known/oauth-protected-resource/mcp`, `/mcp/.well-known/oauth-protected-resource`. Three exact paths, comma-separated frozenset. |
| `memory_service/config.py` | Add two settings: `public_base_url: str = "http://localhost:8000"` and `resource_documentation_url: str = "https://github.com/ollieuk/graph-memory-fabric"` (the latter only if O-1 lands in favour of "make it a setting"; otherwise this row is removed). |
| `memory_service/main.py` | Add a small `_register_discovery_routes(app)` helper called immediately after the `app = FastAPI(...)` line and before `app.mount("/mcp", _mcp_asgi)`. Helper defines a single inner handler returning the JSON dict and registers it on three paths. |
| `.env.example` | Document `PUBLIC_BASE_URL` (and `RESOURCE_DOCUMENTATION_URL` if applicable). Comment notes that production (`memfabric.carr-it.net`) and local dev (`http://localhost:8000`) both work — the value just has to match the actual public origin. |
| `tests/test_wp169_oauth_metadata.py` | **New.** Unit tests for the middleware allow-list and the JSON document shape; integration tests against the live stack. |
| `BACKLOG.md` | Add WP-169 row to "Currently In Progress" with `Started: 2026-05-06`. Add new row to "Prioritised Backlog" at Order=1 (Priority=5.0, Value=H, Effort=L, Depends on `✅ WP-105`). Add description block at the bottom of the "Detail Specs" section in WP-ID order. Other rows shift Order-ID. |

No changes to FastMCP, no changes to `mcp_server/`.

---

## Cypher Patterns

None. WP-169 touches HTTP routing, ASGI middleware, and config only — no graph schema, no queries.

---

## Test Plan

This section is the `engineering:testing-strategy` output for WP-169 and is mandatory before any code is written. The skill could not be invoked from this planning agent; I followed its conventions and adapted the WP-150 plan's pattern (which was produced by the same skill) to keep shape consistent.

### Unit tests — `tests/test_wp169_oauth_metadata.py` (no live stack)

Use the same `_run_middleware` helper pattern from `tests/test_wp105_mcp_http.py`. Pure unit tests for `BearerTokenMiddleware` allow-list logic plus the response-shape contract.

| ID | Test | Verifies |
|----|------|----------|
| U-MW-1 | `test_middleware_passes_through_well_known_path_with_no_token` | Scope path `/.well-known/oauth-protected-resource`; no Authorization header; `api_keys=frozenset({"some-key"})`. Middleware returns 200 (inner app reached). |
| U-MW-2 | `test_middleware_passes_through_well_known_path_with_invalid_token` | Same as U-MW-1 but with `Bearer wrong-token`. Still 200 — discovery routes never check the token. |
| U-MW-3 | `test_middleware_passes_through_mcp_well_known_path` | Scope path `/.well-known/oauth-protected-resource` (mounted form, the rewrite Starlette does for `/mcp/.well-known/...`). 200 with no token. |
| U-MW-4 | `test_middleware_blocks_non_well_known_path_unchanged` | Scope path `/tools/call`; no token; `api_keys` non-empty. 401 — regression guard. |
| U-MW-5 | `test_middleware_blocks_well_known_path_substring_lookalike` | Scope path `/foo/.well-known/oauth-protected-resource-evil`; no token. 401. Confirms suffix matching is exact, not substring. |
| U-MW-6 | `test_middleware_blocks_well_known_query_param_smuggle` | Scope path `/tools/call`, query string `?path=/.well-known/oauth-protected-resource`; no token. 401. (Defence in depth — the middleware reads `scope["path"]`, not query string, but this test pins the behaviour.) |
| U-AUTH-6 | `test_verify_api_key_allows_well_known_paths_in_open_paths` | Mock a `Request` with `url.path = "/.well-known/oauth-protected-resource"`; `verify_api_key(request)` returns without raising. |
| U-AUTH-7 | `test_verify_api_key_allows_mcp_well_known_path` | Same with `/mcp/.well-known/oauth-protected-resource`. Returns. |
| U-AUTH-8 | `test_verify_api_key_blocks_other_paths_unchanged` | Path `/memory/search`, no token, `api_keys` non-empty. Raises 401. Regression guard. |
| U-DOC-1 | `test_metadata_document_shape` | Call the handler directly (`_oauth_protected_resource_metadata()`); assert keys: `resource`, `authorization_servers`, `bearer_methods_supported`, `resource_documentation`. Asserts `authorization_servers == []` and `bearer_methods_supported == ["header"]`. |
| U-DOC-2 | `test_metadata_resource_url_uses_public_base_url` | Set `settings.public_base_url = "https://example.com"`, call handler, assert `resource == "https://example.com/mcp/"`. |
| U-DOC-3 | `test_metadata_resource_url_strips_trailing_slash_on_base` | Set `settings.public_base_url = "https://example.com/"` (with trailing slash), call handler, assert `resource == "https://example.com/mcp/"` (single slash, no `//`). |
| U-DOC-4 | `test_metadata_is_json_serialisable` | `json.dumps(handler_result)` succeeds and round-trips. |

### Integration tests — `tests/test_wp169_oauth_metadata.py` (`@pytest.mark.integration`, live stack required)

Stack prerequisites: Memgraph + FastAPI service running at `http://localhost:8000` (or the `PUBLIC_BASE_URL` configured for the test) with `/mcp` mounted and `API_KEYS` set to a non-empty value (so we can verify the allow-list actually carves out an exemption rather than running open-mode). Reuses the `_BASE` and `_get_api_key` helpers from `tests/test_wp105_mcp_http.py`.

| ID | Test | Verifies |
|----|------|----------|
| I-1 | `test_i1_well_known_protected_resource_no_auth_returns_200` | `httpx.get("/.well-known/oauth-protected-resource")` with no Authorization header. Status 200. JSON body has `resource`, `authorization_servers == []`. |
| I-2 | `test_i2_well_known_protected_resource_mcp_no_auth_returns_200` | Same for `/.well-known/oauth-protected-resource/mcp`. Status 200, identical JSON shape. |
| I-3 | `test_i3_mcp_well_known_protected_resource_no_auth_returns_200_NOT_401` | `httpx.get("/mcp/.well-known/oauth-protected-resource")` with no Authorization header. **Status 200, NOT 401.** This is the bug-driver test — the failing-before behaviour was 401 from `BearerTokenMiddleware`. |
| I-4 | `test_i4_mcp_post_with_valid_bearer_still_works` | `POST /mcp/` with valid bearer token + `Accept: application/json, text/event-stream` + minimal `initialize` payload. Status 200 (or 202 SSE accepted). Regression guard for the actual MCP transport. |
| I-5 | `test_i5_mcp_post_with_no_bearer_still_returns_401` | `POST /mcp/` with no token. Status 401. Regression guard: the discovery carve-out must not have leaked into the JSON-RPC path. |
| I-6 | `test_i6_memory_search_with_no_bearer_still_returns_401` | `POST /memory/search` with no token. Status 401. Regression guard: the FastAPI top-level `_OPEN_PATHS` extension must not have leaked beyond the three discovery paths. |
| I-7 | `test_i7_metadata_resource_url_matches_public_base_url` | Read the actual JSON returned by I-1; assert `body["resource"]` starts with the configured `PUBLIC_BASE_URL` and ends with `/mcp/`. Catches the case where the test stack runs with a different `PUBLIC_BASE_URL` than expected. |
| I-8 | `test_i8_metadata_well_known_authorization_server_returns_404` | `httpx.get("/.well-known/oauth-authorization-server")` with no token. Status 404. Pins the explicit decision in step 6 — we do *not* serve AS metadata. If a future SDK release requires it, this test fails first and gives us a deliberate change point. |

### Acceptance Criteria

1. **AC-1 (manual / smoke):** With `API_KEYS` configured and the service restarted, `claude mcp list` shows `memory: ✓ Connected`. Failure mode pre-fix: `memory: ✗ Failed to connect` with SDK error containing `HTTP 404` or `ZodError`.
2. **AC-2 (manual):** Inside a fresh Claude Code session against the live service, `mcp__memory__health_check` (or any `mcp__memory__*` tool) is callable and returns successfully.
3. **AC-3:** `curl https://memfabric.carr-it.net/.well-known/oauth-protected-resource` → 200 + JSON containing `"resource": "https://memfabric.carr-it.net/mcp/"`, `"authorization_servers": []`. (Replace host with whatever the deploy maps to.)
4. **AC-4:** `curl https://memfabric.carr-it.net/mcp/.well-known/oauth-protected-resource` → 200 + same JSON (NOT 401).
5. **AC-5:** `curl https://memfabric.carr-it.net/memory/search -X POST -d '{}'` (no token) → still 401. Regression guard.
6. **AC-6:** All U-* unit tests pass. All I-* integration tests pass against the running live stack (confirmed by the implementer with the actual stack up — not just mocked).
7. **AC-7:** `/simplify` clean, `engineering:deploy-checklist` green, BACKLOG.md updated, retrospective note added.

### Test execution order

1. Run U-* unit tests first — fast, no infra dependency. Must pass before any integration run.
2. Bring up live stack with `API_KEYS` non-empty (e.g. via the existing `docker compose up -d` flow + an `.env` with API_KEYS set). Confirm `POST /mcp/` with bearer still works as a baseline.
3. Run integration tests: `pytest -m integration tests/test_wp169_oauth_metadata.py`.
4. Run AC-1 / AC-2 manual smoke: restart Claude Code, run `claude mcp list`, then call `mcp__memory__health_check` from inside a fresh session.
5. Re-run the full suite once to confirm no regressions in WP-105 (auth tests) or WP-150 (MCP transport tests).

---

## Risks / Open Questions

| ID | Concern | Mitigation |
|----|---------|------------|
| R-1 | Starlette's mount routing precedence: a route registered on `app` at `/mcp/.well-known/oauth-protected-resource` may or may not win against the `/mcp` mount. If the mount wins, the request reaches FastMCP's sub-app, which has no such route, and FastMCP returns 404 (or, after step 2, the BearerTokenMiddleware lets it through to a 404 from FastMCP's router). | Verify empirically during implementation (step 5 of Approach). If mount wins, register the metadata handler as a FastMCP route OR insert a small Starlette route ahead of the mount via `app.router.routes.insert(0, ...)`. The implementer has explicit permission to choose either fallback. The unit tests U-MW-3 + integration test I-3 both surface this if it goes wrong. |
| R-2 | The bearer-token allow-list could be widened by accident in future edits, exposing the MCP transport. | Tight suffix matching, U-MW-5/U-MW-6 regression tests, `/simplify` review. |
| R-3 | RFC 9728 spec evolution — future Claude Code SDK versions may require additional fields (e.g. `dpop_signing_alg_values_supported`, `tls_client_certificate_bound_access_tokens`). | Out of scope. The current document is RFC 9728 §3 minimum-viable. If SDK upgrades break it, file a follow-up WP. |
| R-4 | `public_base_url` mismatch between test config and live config. If a test bakes in `http://localhost:8000` and the stack runs at `https://memfabric.carr-it.net`, I-7 fails for the wrong reason. | I-7 reads `settings.public_base_url` at test time and asserts the response matches; doesn't hard-code a URL. |
| R-5 | If the implementer accidentally registers the discovery routes via `include_router(..., dependencies=[])` rather than extending `_OPEN_PATHS`, the dependencies on `app` still apply (FastAPI dependency inheritance is from the app, not just from sub-routers). | Approach explicitly chooses `_OPEN_PATHS` extension. The integration test I-1 fails if this is wrong (returns 401, not 200). |
| O-1 | `resource_documentation_url`: setting or hardcoded literal? | **Recommendation: hardcoded literal in the handler.** Repo URL is fixed; making every cosmetic string a setting bloats `Settings`. If we ever need to change it, it's one line in `main.py`. Implementer can deviate if a clear reason emerges, but plan defaults to hardcoded. |
| O-2 | Should we serve `/.well-known/oauth-authorization-server` as a stub? | **Recommendation: no, see step 6 of Approach.** RFC 9728 says clients should not probe AS when `authorization_servers: []`. If post-implementation manual testing (AC-1) shows the SDK still probes and fails, file a follow-up WP. I-8 pins the current behaviour so the change point is deliberate. |
| O-3 | Is the SDK actually consuming `bearer_methods_supported`? | Unknown but cheap to include and spec-mandated for the metadata document. Costs nothing to set. |

---

## Reuse / Patterns Identified

- **Allow-list pattern for auth bypass:** `memory_service/auth.py::_OPEN_PATHS` already exists for `/health`. WP-169 reuses it for the three discovery paths. No new mechanism, no new file.
- **Test scaffolding:** `tests/test_wp105_mcp_http.py::_run_middleware`, `_BASE`, `_get_api_key` reused directly. Add `@pytest.mark.integration` per the CLAUDE.md gotcha.
- **Settings pattern:** `pydantic-settings` with `.env` loading is established. New `public_base_url` setting follows the existing convention (default sensible for local dev, env-overridable for prod).
- **No existing `.well-known/*` routes in the repo** — this is the first. Confirms the discovery code lives in `main.py` rather than in any feature-specific module.

---

## FastAPI / Starlette Compatibility Notes

Verified against the project's pinned versions (FastAPI 0.116.x, Starlette 0.40.x as of the most recent `requirements.txt` revision):

- `app.dependencies=[Depends(...)]` is applied to *every* route registered on the app, including those added via `include_router(...)`. There is no `dependencies_overrides` mechanism that bypasses dependency inheritance per-route without reaching into the dependency at runtime. **`_OPEN_PATHS` allow-list inside the dependency itself is the documented bypass pattern.**
- ASGI mount path rewriting: when `app.mount("/mcp", sub_app)` is in effect, requests to `/mcp/foo` reach `sub_app` with `scope["path"] == "/foo"` and `scope["root_path"] == "/mcp"` (or the equivalent — Starlette computes both). The bearer middleware wraps `sub_app`, so it sees the rewritten `/foo`-style path. **This is why the suffix allow-list in step 2 matches `/.well-known/oauth-protected-resource`, not `/mcp/.well-known/oauth-protected-resource`.**

---

## Rollback Path

Single-commit rollback. If the metadata document or the allow-list causes unexpected client behaviour:

1. `git revert <commit>` reverses:
   - The `_DISCOVERY_PATH_SUFFIXES` addition in `mcp_auth.py`.
   - The `_OPEN_PATHS` extension in `auth.py`.
   - The `_register_discovery_routes` call site and helper in `main.py`.
   - The two new settings in `config.py` (and `.env.example` documentation).
   - The new test file.
2. No data migration, no schema change, no operational state. Discovery paths revert to 404 / 401, and Claude Code MCP discovery breaks again — same as current state. No silent corruption risk.
3. Implementer must keep the change atomic (single commit, all sites + new test) so revert is one operation.

---

## R-1 Resolution

**Empirically verified 2026-05-06 during implementation:**

Routes registered on the top-level `app` via `app.add_api_route(...)` **before** the `app.mount("/mcp", _mcp_asgi)` call **win** over the mount for paths that are more specific than `/mcp`. Starlette evaluates routes in registration order; a `Route` at `/mcp/.well-known/oauth-protected-resource` is matched before the `Mount` at `/mcp` because it appears earlier in `app.routes`.

Verification: after registering the three discovery routes and calling `app.mount("/mcp", _mcp_asgi)`, `GET /mcp/.well-known/oauth-protected-resource` with no token returned `200` + valid JSON (not `401` from `BearerTokenMiddleware` and not `404` from FastMCP).

**Implementation strategy used:** `app.add_api_route(path, handler, methods=["GET"])` for all three paths, called in a loop before `app.mount("/mcp", ...)`. No sub-router needed; no insertion into `app.router.routes` at index 0 needed. The discovery routes bypass `verify_api_key` via `_OPEN_PATHS` extension in `auth.py`, and bypass `BearerTokenMiddleware` via the `_DISCOVERY_PATH_SUFFIXES` allow-list in `mcp_auth.py` (for the `/mcp/.well-known/...` path — though it turned out the top-level route matched first, the middleware allow-list is still needed as defence-in-depth).

---

## Acceptance Evidence

Recorded 2026-05-06 against live local stack (http://localhost:8000) with API_KEYS configured (non-empty).

```
# Curl 1: /.well-known/oauth-protected-resource/mcp — 200 + JSON
HTTP/1.1 200 OK
content-type: application/json
{"resource":"http://localhost:8000/mcp/","authorization_servers":[],"bearer_methods_supported":["header"],"resource_documentation":"https://github.com/ollieuk/graph-memory-fabric"}

# Curl 2: /mcp/.well-known/oauth-protected-resource — 200 + JSON (was 401 before WP-169)
HTTP/1.1 200 OK
content-type: application/json
{"resource":"http://localhost:8000/mcp/","authorization_servers":[],"bearer_methods_supported":["header"],"resource_documentation":"https://github.com/ollieuk/graph-memory-fabric"}

# Curl 3: POST /mcp/ with valid bearer + initialize — 200 SSE (regression guard)
HTTP/1.1 200 OK
content-type: text/event-stream
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{...},"serverInfo":{"name":"graph-memory-fabric","version":"3.2.4"}}}

# Curl 4: POST /memory/search without token — 401 (regression guard)
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Invalid or missing API key"}
```

AC-1 / AC-2 (claude mcp list + tool call): **Pending user confirmation after prod deploy.** This is a manual step the user must verify post-deploy.

---

## Out of Scope

- Authorization server metadata (`/.well-known/oauth-authorization-server`) — see O-2.
- Implementing an actual OAuth flow (token exchange, refresh, AS endpoints).
- Changes to `.mcp.json` client config — the static-bearer mechanism stays.
- Generalising allow-list mechanism beyond what `_OPEN_PATHS` already provides.
- Refactoring `BearerTokenMiddleware` beyond adding the suffix allow-list.

---

## Definition of Done (from CLAUDE.md)

1. Test plan above is attached to this plan file (this section).
2. Unit tests U-MW-1..U-MW-6, U-AUTH-6..U-AUTH-8, U-DOC-1..U-DOC-4 written and passing.
3. Integration tests I-1..I-8 written and run against the live stack (Memgraph + FastAPI + `API_KEYS` non-empty).
4. AC-1 + AC-2 manually verified: `claude mcp list` shows green, `mcp__memory__health_check` callable from a fresh session.
5. `/simplify` run on the diff; findings actioned or deferred.
6. `engineering:deploy-checklist` green.
7. BACKLOG.md: WP-169 moved from "Currently In Progress" to Completed; retrospective note added; description block migrated to CHANGELOG on completion.
8. Git commit: `WP-169: OAuth protected-resource metadata for MCP discovery` (created from Git Bash on Windows per CLAUDE.md).
