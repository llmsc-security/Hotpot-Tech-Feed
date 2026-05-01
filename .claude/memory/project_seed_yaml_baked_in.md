---
name: seed_sources.yaml is baked into the backend image
description: Editing the YAML alone is not enough — the backend Docker image carries the file, and entrypoint reseeds on every start.
type: project
---

`backend/data/seed_sources.yaml` is **copied into the backend image**, not volume-mounted. `docker-entrypoint.sh` runs `hotpot seed-sources` on every container start. Two consequences:

1. After editing the YAML, you must `docker compose build backend && docker compose up -d backend` for the new entries to take effect.
2. `seed_from_yaml()` matches existing rows by **URL**, not name. If you change a Source.url in the DB without also updating the YAML, the next container start creates a duplicate row (the seeder finds no URL match and inserts fresh). Always update the YAML to match any in-DB URL surgery.

**Why:** Lost a couple of hours to duplicate sources because SQL UPDATEs to `Source.url` left the YAML stale.

**How to apply:** Whenever you add/rename/repair a source, update the YAML in the same commit; rebuild backend; only then run `hotpot seed-sources` or restart.
