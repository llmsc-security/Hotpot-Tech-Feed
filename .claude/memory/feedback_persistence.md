---
name: Persistence is non-negotiable
description: Every deploy / migration / rebuild change must keep user data intact and ship explicit backup/restore tooling.
type: feedback
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
Treat user data (Postgres corpus, contributions, source health) as load-bearing. Any change that touches the deploy, compose stack, or container lifecycle must:
1. Preserve named volumes (`hotpot_pg`, `hotpot_redis`, `hotpot_qdrant`) — never `docker compose down -v`, never recreate the postgres container in a way that drops the volume.
2. Provide explicit cross-host migration tooling — `backup.sh`/`restore.sh` at repo root, pg_dump-based, portable archive.
3. Confirm the corpus survived after restart by hitting `/api/stats` (item count) before reporting "done".

**Why:** The user said *"make sure the state has saved, e.g. migrate to another pc, the server need to deploy again, and didnot loss the user data"* and earlier *"make sure you have saved the user data"* — they explicitly worry about volumes vanishing during refactors. Earlier in the session, a TRUNCATE was done deliberately for a clean re-tag; the user accepted it because we had volumes and ingest could rebuild — not because data loss is OK in general.

**How to apply:**
- Refactoring start.sh / docker-compose.yml: cite which named volumes are preserved and verify with `docker volume ls | grep hotpot` after the change.
- Adding new persistent state (a new table, a new collection): also extend `backup.sh` to capture it and `restore.sh` to restore it.
- Recommend `bash backup.sh` before any risky operation (volume rename, compose project rename, postgres major bump).
