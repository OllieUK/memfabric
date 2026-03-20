## 0. Project title and elevator pitch

**Title:** Graph‑Memory Fabric – Local, Model‑Agnostic Long‑Term Memory with Graph‑Cloud Visualisation for Multiple Agents

**Pitch:**  
Build a local‑first memory service that represents all “memories” as graph nodes with vector embeddings, exposes a simple HTTP/MCP API for multiple independent agents, and provides a live graph‑cloud visualisation. In **v1**, the only LLM is your current IDE/session (Claude Code / Codex) acting as a copilot; the runtime stack has no hard dependency on external LLM APIs. In later phases, you can attach headless agents and mobile/remote clients without changing the core graph‑vector design. [memgraph](https://memgraph.com/blog/memgraph-3-4-release-announcement)

***

## 1. Goals and non‑goals

### 1.1 Primary goals (v1)

- Provide a **long‑term memory layer** for agents, independent of any specific language model or API.
- Represent memories as **nodes in a graph** with:
  - Text summaries.
  - Vector embeddings.
  - Types, tags, timestamps, and explicit relationships between memories. [marktechpost](https://www.marktechpost.com/2025/11/10/comparing-memory-systems-for-llm-agents-vector-graph-and-event-logs/)
- Support **multiple conceptual agents** (SecurityAdvisor, ProjectManager, LeadershipCoach, etc.) that can read/write to the same memory fabric via a clean API, even if in v1 those “agents” are just scripts you run with LLM assistance.
- Allow **semantic search + graph traversal**:
  - Vector similarity search to find seed memories.
  - Graph expansion to pull context via edges (RELATED_TO, DEPENDS_ON, etc.). [arxiv](https://arxiv.org/html/2601.03236v1)
- Provide a **visual graph‑cloud** UI:
  - Nodes as memories.
  - Colours and shapes for agent/project/type.
  - Edges as relationships.
- Keep the LLM **entirely outside** the runtime in v1:
  - All “intelligence” is in how you use Claude Code / Codex while editing and running scripts.
  - The memory service itself is text‑in/text‑out, plus embeddings.

### 1.2 Future goals (v2+)

- Add **headless agents** (background processes) that call both:
  - The Memory API.
  - External LLM APIs (Claude, OpenAI, local Ollama).
- Add **mobility/remote access**:
  - Central memory service reachable from multiple machines/devices.
  - Optional offline‑first / sync patterns for laptops and mobile.

### 1.3 Non‑goals (v1)

- No server‑side LLM calls inside the Memory Service.
- No multi‑tenant access control beyond your local environment.
- No heavy orchestration framework (LangGraph/AutoGen etc.) initially.

***

## 2. Target environment

- **Host:** Windows 11 desktop.
- **Subsystem:** WSL2 (Ubuntu 22.04 LTS).
- **Containers:** Docker Desktop (Linux containers).
- **LLM usage in v1:**  
  - Only via your **current coding session** (Claude Code, Codex, Perplexity Computer Use).
  - LLM writes code, refactors, and helps design prompts; it is not called from within the running services.
- **Optional LLM backends in v2+:**
  - Anthropic Claude API.
  - OpenAI API.
  - Local Ollama.

All services (Memgraph, Memory Service) must run locally via `docker compose up` or simple CLI commands from WSL.

***

## 3. High‑level architecture

### 3.1 Components (v1)

1. **Graph‑Vector Database (Memgraph)**  
   - Single engine storing:
     - Nodes (`Memory`, `Agent`, `Person`, `Project`).
     - Edges (`RELATED_TO`, `DEPENDS_ON`, `PRODUCED_BY`, `ABOUT`).
     - Vector embeddings on `Memory` nodes, indexed via Memgraph’s native vector index. [memgraph](https://memgraph.com/docs/querying/vector-search)
   - Offers:
     - Vector search procedures (e.g. `CALL vector_search.search(...)`). [memgraph](https://memgraph.com/blog/simplify-data-retrieval-memgraph-vector-search)
     - A built‑in Web UI (Memgraph Lab) for graph‑cloud visualisation and Cypher‑like querying. [developers.llamaindex](https://developers.llamaindex.ai/python/examples/property_graph/property_graph_memgraph/)

2. **Memory API Service (Python + FastAPI)**  
   - Runs in WSL or Docker.
   - Responsibilities:
     - Accept memory text and metadata.
     - Generate embeddings via a **local embedding model** (e.g. `sentence-transformers`) – no external API needed. [memgraph](https://memgraph.com/blog/build-movie-similarity-search-vector-search-memgraph)
     - Create/query/update Memgraph nodes/edges and invoke vector search.
   - Exposes minimal HTTP interface:
     - `POST /memory` – add/update memory nodes.
     - `GET /memory/search` – semantic + graph search.
     - `GET /memory/graph` – export subgraph for visualisation.

3. **Local Python Client + Scripts**  
   - `memory_client.py` wraps the HTTP API.
   - Example scripts:
     - `add_memory_from_markdown.py`
     - `search_memory_cli.py`
   - You and the in‑session LLM use these to:
     - Summarise notes.
     - Tag and store decisions.
     - Retrieve context.

4. **LLM‑in‑IDE Only (v1)**  
   - No `LLMClient` code in the runtime.
   - When a task needs reasoning or summarisation:
     - You ask Claude Code / Codex to:
       - Read files.
       - Call `memory_client`.
       - Generate summaries.
       - Propose edge relationships.
     - The LLM’s “agentic” behaviour happens via your prompts and its edits, not as a background service call.

### 3.2 Components added in v2+

When ready to go beyond IDE‑only:

- **LLM Client Abstraction Layer:**
  - `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama.
- **Headless Agents (Python services / workers):**
  - Use `memory_client` and `LLMClient` to run without you present.
- **Remote/Mobile front‑ends:**
  - Web/mobile apps using `GET /memory/...` and `POST /memory`.

The Memory Service and Memgraph remain unchanged; you only add new consumers.

***

## 4. Data model (schema)

### 4.1 Node types

- `Memory`
  - `id: UUID`
  - `fact: str` – the raw, observable fact or statement. e.g. *"Oliver has ADHD."*
  - `so_what: str | None` – the impact or meaning of the fact. e.g. *"Structure and short feedback loops matter more than motivation."* Optional; not all memory types have a meaningful consequence.
  - `text: str` – derived embedding target: `fact + " " + so_what` (or just `fact` if no `so_what`). Used for vector search; not a user-authored field.
  - `type: str` – `"fact" | "decision" | "insight" | "todo" | "event" | "observation"`.
  - `tags: list[str]` – topics/projects, e.g. `["security","IAM"]`.
  - `created_at: datetime`
  - `last_used_at: datetime`
  - `importance: int` – 1–5, for prioritisation/pruning.
  - `strength: float` (0–1) – current reinforcement level. Seeded from `importance / 5.0` at creation. Incremented on recall and explicit reinforcement; decays exponentially over time when not recalled (Ebbinghaus forgetting curve). Used as a secondary ranking signal in search.
  - `recall_count: int` – total number of times this memory has appeared in a search result. Monotonically increasing; never decays.
  - `reinforcement_count: int` – total number of explicit reinforcement signals received.
  - `last_reinforced_at: datetime` – anchor timestamp for decay calculation.
  - `decay_rate: float` – per-memory decay rate; defaults to global `MEMORY_DECAY_RATE` config. Lower values make a memory stickier.
  - `embedding: list[float]` – vector used by Memgraph’s vector index. [memgraph](https://memgraph.com/docs/querying/vector-search)

- `Agent`
  - `id: str` – logically unique name (`"SecurityAdvisor"`, `"LeadershipCoach"`).
  - `name: str`
  - `purpose: str`

- `Person`
  - `id: str`
  - `name: str`
  - `role: str | None`

- `Project`
  - `id: str`
  - `name: str`
  - `domain: str` – `"security"`, `"leadership"`, etc.

### 4.2 Edge types

- `RELATED_TO (Memory -> Memory)`
  - `weight: float` (0–1) – reinforceable activation strength. Set at creation from vector similarity score; incremented each time the edge is traversed in a retrieval; decays over time if not activated.
  - `relation_type: str` – `"semantic" | "temporal"`.
  - `activation_count: int` – number of times traversed in a retrieval session.
  - `last_activated_at: datetime` – anchor for edge decay calculation.
  - `decay_rate: float` – per-edge decay rate; defaults to `EDGE_DECAY_RATE` config (slower than node decay by default).
  - Auto-created by vector search on ingestion. Symmetric in intent; directional in storage. Edges that are never activated will decay below the prune threshold and be excluded from graph expansion.

- `LEADS_TO (Memory -> Memory)`
  - Explicit causal edge: *this fact produces or enables that consequence.* Directional and asymmetric.
  - Carries the same reinforcement properties as `RELATED_TO`: `weight`, `activation_count`, `last_activated_at`, `decay_rate`.
  - Created explicitly on ingestion via `cause_ids` / `effect_ids`, or auto-created when `create_effect_node=true` and a `so_what` is provided.
  - Enables backwards traversal ("why is this true?") and forwards traversal ("what does this affect?").
  - Example: `(Oliver has ADHD) -[:LEADS_TO]-> (Oliver responds well to structure)` and `(Oliver trained as engineer) -[:LEADS_TO]-> (Oliver responds well to structure)`.

- `PRODUCED_BY (Memory -> Agent)`
  - Which logical agent generated this memory.

- `ABOUT (Memory -> Person | Project)`
  - Which person/project this memory concerns.

- `IN_STRAND (Memory -> Strand)`
  - `weight: float` (0–1) – strength of association. Primary strand = 1.0; secondary strands carry lower weights.
  - Every Memory must have at least one `IN_STRAND` edge (primary strand).

***

## 5. Semantics and usage patterns (v1)

- **Vector‑only links first:**
  - When inserting a new Memory, the Memory Service:
    - Computes its embedding from `text` (= `fact + so_what`) locally.
    - Uses Memgraph’s vector search to find K nearest neighbours.
    - Creates `RELATED_TO` edges to these neighbours (associative, auto-linked).

- **Causal graph — fact + so_what + LEADS_TO:**
  - Every memory has a `fact` (what is true) and optionally a `so_what` (why it matters / what it causes).
  - When a `so_what` is significant enough to be its own traversable node, it is stored as a separate Memory and linked with a `LEADS_TO` edge.
  - Multiple cause nodes can converge on a single consequence node. A consequence can itself be a cause further downstream, forming a directed causal chain:
    ```
    (Oliver has ADHD) ──LEADS_TO──► (Oliver responds well to structure)
    (Oliver trained as engineer) ──LEADS_TO──► (Oliver responds well to structure)
    (Oliver responds well to structure) ──LEADS_TO──► (Oliver enjoys D&D)
    (Oliver responds well to structure) ──LEADS_TO──► (Oliver uses Notion + checklists)
    ```
  - This enables two traversal modes:
    - **Upstream** ("why is this true?"): follow `LEADS_TO` edges backwards to find contributing causes.
    - **Downstream** ("what does this affect?"): follow `LEADS_TO` edges forwards to find consequences.
  - `LEADS_TO` is complementary to `RELATED_TO`: related-to is semantic proximity; leads-to is explicit causation.

- **Strand membership:**
  - Every Memory must be assigned to at least one Strand (primary, `weight=1.0`).
  - Secondary strand connections can be added with lower weights (0.5–0.9) reflecting partial relevance.
  - Strands are the thematic spokes of the Memory Web: Core Life Domains, Companion Domain, Shadow Domain.

- **Memory reinforcement — spaced repetition for facts:**
  - Every memory has a `strength` (0–1) that starts seeded from its `importance` and evolves over time.
  - Two reinforcement signals exist:
    - **Recall** (automatic): every time a memory appears in a search result, the server increments its `strength` slightly and updates `recall_count`. No caller action needed.
    - **Explicit** (caller-initiated): when the caller confirms a memory was actually used (`POST /memory/{id}/reinforce`), a larger strength increment is applied. This is the higher-quality signal.
  - Between reinforcements, `strength` decays exponentially — the Ebbinghaus forgetting curve:
    ```
    effective_strength = strength × exp(-decay_rate × days_since_last_reinforced)
    ```
  - `effective_strength` is computed at query time (not stored) and used as a secondary ranking signal: at equal vector distance, stronger memories rank higher.
  - A configurable floor (`MIN_MEMORY_STRENGTH`) can exclude fully-decayed memories from search results entirely, creating a natural long-term memory horizon.

- **Edge reinforcement — Hebbian learning:**
  - Edges between memories strengthen each time they are traversed together in a retrieval session ("neurons that fire together, wire together").
  - Two activation signals mirror the node model:
    - **Traversal** (automatic): graph expansion traversals (`max_hops > 0`) increment `activation_count` and `weight` on each edge crossed.
    - **Co-reinforcement** (caller-initiated): when an explicit reinforcement names `co_recalled_ids`, all edges connecting the reinforced memory to those co-recalled memories receive a larger weight increment.
  - Edge `weight` also decays over time (at a slower default rate than node `strength`, so connections persist longer than individual memories).
  - Edges that decay below `EDGE_PRUNE_THRESHOLD` are excluded from graph expansion — dormant but not deleted. A maintenance sweep can hard-delete edges below a minimum floor.
  - The combined effect: the graph self-organises over time. Frequently confirmed connections become highways; speculative auto-linked edges that are never confirmed quietly fade.

- **LLM‑assisted edge refinement (in‑session):**
  - You ask Claude Code to inspect top neighbours and propose which should be `LEADS_TO` (causal) vs `RELATED_TO` (associative), and with which weights.
  - You then approve/edit those suggestions and run a script to update the graph accordingly.

- **Agent separation via tags and edges:**
  - Memories are tagged with logical `agent_id`, `strand_ids`, `project_id`, etc.
  - v2 agents and visual filters use these to distinguish which area of life they belong to.

***

## 6. External interfaces (Memory API)

### 6.1 HTTP endpoints

1. `POST /memory`
   - Request:
     - `text: str`
     - `type: str`
     - `tags: list[str]`
     - `agent_id: str`
     - `project_id: str | None`
     - `person_ids: list[str]`
     - `importance: int | None`
     - `related_ids: list[str] | None`
   - Behaviour:
     - Call local embedding model to get `embedding`. [memgraph](https://memgraph.com/blog/build-movie-similarity-search-vector-search-memgraph)
     - Upsert `Agent`, `Project`, `Person` nodes.
     - Create `Memory` node with properties.
     - Create `PRODUCED_BY` / `ABOUT` edges.
     - If `related_ids` provided:
       - Create `RELATED_TO` or `DEPENDS_ON` edges accordingly.
     - Else:
       - Run vector search for nearest neighbours and create default `RELATED_TO` edges.
   - Response:
     - `{"memory_id": "..."}`

2. `GET /memory/search`
   - Params:
     - `query: str`
     - `tags: list[str] | None`
     - `agent_ids: list[str] | None`
     - `project_ids: list[str] | None`
     - `limit: int = 10`
     - `max_hops: int = 1`
   - Behaviour:
     - Compute query embedding locally.
     - Run Memgraph vector search on `Memory.embedding`. [memgraph](https://memgraph.com/blog/simplify-data-retrieval-memgraph-vector-search)
     - Apply filters.
     - Optionally traverse 1–`max_hops` edges to expand context.
   - Response:
     - List of Memory objects with neighbour info.

3. `GET /memory/graph`
   - Params (optional filters):
     - `project_id`, `agent_id`, `tag`, `since`, `until`.
   - Response:
     - `{nodes: [...], edges: [...]}` for front‑end or ad‑hoc tools.

### 6.2 Python client (for scripts & IDE)

- `memory_client.py`:
  - `add_memory(...)`
  - `search_memory(...)`
  - `get_graph(...)`

Example uses inside Claude Code sessions:

- “Generate a script that takes `notes/today.md`, summarises it into 5 ‘insight’ memories, and calls `memory_client.add_memory` for each.”  
- “Given this `query`, use `memory_client.search_memory` and print top 5 results with neighbours.”

***

## 7. Implementation phases (explicitly v1 = no server‑side LLM calls)

You can ask Claude Code / Codex to walk through these phases.

### Phase 1 – Environment and Memgraph

- Create `docker-compose.yml` that:
  - Launches Memgraph Platform (DB + MAGE + Lab).
  - Exposes ports `7687` (Bolt) and `7444` (HTTP/Lab UI). [memgraph](https://memgraph.com/docs/)
- Verify:
  - From WSL Python: connect and create a trivial node.
  - From browser: open Memgraph Lab at `http://localhost:3000` and see empty graph.

### Phase 2 – Schema and vector index

- Define Cypher schema for labels and properties:
  - `Memory`, `Agent`, `Person`, `Project`.
- Configure node vector index on `Memory(embedding)` using Memgraph’s `CREATE VECTOR INDEX ...` syntax. [memgraph](https://memgraph.com/docs/querying/vector-search)
- Write a minimal Python test:
  - Insert one Memory with a random vector.
  - Query via `CALL vector_search.search(...)`. [github](https://github.com/memgraph/ai-demos/blob/main/retrieval/vector-search/vector_search_example.ipynb)

### Phase 3 – Local embeddings

- Add local embedding support:
  - Use `sentence-transformers` in Python (e.g. `all-MiniLM-L6-v2`). [memgraph](https://memgraph.com/blog/build-movie-similarity-search-vector-search-memgraph)
- Implement `get_embedding(text: str) -> list[float]`:
  - Load model once on startup.
  - Optional: simple on‑disk cache to avoid recomputing unchanged texts.

### Phase 4 – Memory API (FastAPI, no LLM inside)

- Scaffold FastAPI app with:
  - `POST /memory`
  - `GET /memory/search`
  - `GET /memory/graph`
- Implement endpoints:
  - Use `get_embedding` for text and queries.
  - Use Memgraph driver/connector to:
    - Insert nodes and edges.
    - Create/update vector index entries.
    - Run vector search and graph traversal. [memgraph](https://memgraph.com/docs/fundamentals/indexes)

### Phase 5 – Python client + CLI

- Implement `memory_client.py` that wraps HTTP.
- Add a Typer‑based CLI:
  - `add-memory`
  - `search-memory`
  - `dump-graph` (JSON export).
- Use Claude Code / Codex to:
  - Generate boilerplate.
  - Refactor as needed.

### Phase 6 – In‑session LLM workflows

- Define repeatable patterns/prompts for your IDE LLM:
  - “Summarise this log file into N Memory records and store them via `memory_client`.”
  - “Given past memories for project X, propose 3 new todos and call `add_memory` with type='todo'.”
- These are just usage patterns; no runtime changes.

***

## 8. Future phases: API‑based agents and mobility

### Phase 7 – LLMClient and headless agents (v2+)

- Add `LLMClient` abstraction with implementations for:
  - Claude.
  - OpenAI.
  - Ollama.
- Implement headless agents:
  - `BaseAgent` using `memory_client` + `LLMClient`.
- Run:
  - Nightly or event‑driven tasks (reflections, planning, summarisation) that write back into the fabric.

### Phase 8 – Centralisation and mobile/remote access

- Option A: Central Memory Service
  - Host Memgraph + Memory Service on:
    - Home NUC with Tailscale/WireGuard.
    - Or small VPS.
  - Point all devices’ `memory_client` at this URL (with TLS/API keys).
- Option B: Offline‑first / sync
  - Maintain local append‑only logs of mutations.
  - Replay into a central instance when online (lightweight event log / CRDT‑style). [reddit](https://www.reddit.com/r/AI_Agents/comments/1nkx0bz/everyones_trying_vectors_and_graphs_for_ai_memory/)

### Phase 9 – Custom visual graph‑cloud UI

- Keep Memgraph Lab as default visualiser. [developers.llamaindex](https://developers.llamaindex.ai/python/examples/property_graph/property_graph_memgraph/)
- Optionally:
  - Build a small React/Vue front‑end that consumes `GET /memory/graph`.
  - Use D3.js / vis‑network to render interactive graph clouds filtered by tag/agent/project.
