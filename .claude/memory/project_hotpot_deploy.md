---
name: Hotpot Tech Feed deploy shape
description: Single-host-port nginx-only deploy at HOST_PORT=50002; ingest concurrency capped at 32 to protect the LLM endpoint.
type: project
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
Deploy invariants for this repo:
- **Only `gateway` (nginx) maps to the host.** Everything else (backend, postgres, redis, qdrant) lives on the `internal` docker network with no host port mapping. Adding a new host-facing port is a deliberate change, not a default.
- **HOST_PORT defaults to 50002** (set in `.env`). nginx serves the React SPA at `/` and reverse-proxies `/api/*` (strips the `/api` prefix) to `backend:8000`.
- **Ingest concurrency = `max(1, min(32, cpu_count // 2))`.** Hard cap on 32 even on a 256-core box. Without the cap, parallel LLM enrichment saturates the upstream Qwen endpoint and triggers 502 storms.
- **DB pool sized to workers**: `pool_size = max(20, ingest_workers + 8)`, `max_overflow = 64`. Each enrichment worker takes its own session for the duration of one item.
- **Per-item enrichment is the bottleneck**, not source fan-out. Source-level concurrency (`ingest_source_workers`) defaults to 1; only bump it if the upstream LLM has lots of headroom.

**Why:** Set during the initial parallelization work. The 256-core host kept exhausting the LLM endpoint when defaulted to cpu/2 = 128 threads; the cap was the user's request after seeing 502s.

**How to apply:**
- Don't expose new ports without asking. If you need backend access for debugging, use `docker compose exec backend bash`.
- Don't raise the ingest_workers cap without explicit user request. Users with weaker LLM endpoints would be hurt; users with stronger endpoints can override per-call with `--workers N`.
- When changing `pool_size`, recheck against `ingest_workers` — they're coupled.
