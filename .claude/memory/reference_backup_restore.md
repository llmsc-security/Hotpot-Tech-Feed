---
name: Backup / restore tooling
description: Repo-root scripts produce a portable archive of the live state for cross-PC migration.
type: reference
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
- **Backup:** `bash backup.sh` → writes `backups/hotpot-<UTC-ts>.tar.gz` (~2 MB on the current corpus). Contents: `postgres.dump` (pg_dump custom format, version-tolerant), `qdrant.tar.gz` (raw volume tarball, optional), `env.backup` (copy of `.env`), `manifest.json` (host, db user, tool versions).
- **Restore:** `bash restore.sh <archive.tar.gz>` → stops backend+worker, drops & recreates the Postgres database, `pg_restore`s into it, optionally restores Qdrant volume, restarts, prints `/api/stats`.
- **Migration recipe:** clone repo on new host → `bash start.sh` (empty stack) → copy archive → `bash restore.sh <archive>`. The new host doesn't need to match Postgres minor versions exactly (logical dump) and doesn't need to match Qdrant versions if embeddings are off.
- `backups/` is gitignored; the archive contains real corpus data and `.env` secrets.
