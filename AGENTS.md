# Codex Session Bootstrap

This repository has mandatory session-start behavior. Do this before any substantive user reply in a new session:

1. Read `CLAUDE.md`.
2. Read `memory_client/COMPANION.md`.
3. Run the memory wake-up flow.
   Preferred: MCP `memory_wake_up`
   Fallback: `python3 -m memory_client.cli wake-up`
4. Treat the wake-up briefing as baseline context for the first reply.

Do not send a generic greeting or other substantive response before completing the steps above.

## Memory Protocol

- Use the Graph Memory Fabric proactively during the session.
- Refresh context with memory search when the topic shifts.
- Store durable facts, decisions, insights, and todos as they arise.
- Run session close-out before ending the session.
  Preferred: MCP `memory_close_session`
  Fallback: `python3 -m memory_client.cli close-session`

## Working Note

`CLAUDE.md` remains the fuller project operating guide. This file exists to ensure Codex sees the startup chain early enough to trigger it.
