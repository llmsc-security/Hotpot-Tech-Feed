---
name: Brisk workflow, casual commits
description: User sends terse one-line asks and expects action; "git push" means stage+commit+push, and short commit messages are fine in this repo.
type: feedback
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
Workflow style for this user:
- Asks come as one-line commands ("git push", "hotpot ingest-now", "change the port to 50002 ..."). Do the action; don't ask for confirmation on standard dev steps.
- `git push` with uncommitted changes implies "commit everything sensible, then push." Existing repo history has commit messages like `f` and `Initial commit` — verbose messages are welcome but the bar is low.
- New feature requests arrive mid-task in succession; expectation is to bundle them into the same rebuild rather than serializing redeploys.
- Long log streams in tool output are tolerated; final summary should be tight (a few bullets, not paragraphs).

**Why:** Inferred from session pattern — the user fired off ~10 follow-up messages while ingest was running, never asked for status updates, and pushed back when summaries got long.

**How to apply:**
- Default to acting + brief end-of-turn summary. Don't pre-confirm reversible local actions (edits, builds, restarts).
- For destructive or upstream-visible actions (push, force-push, prod deploy, dropping volumes), still confirm — but `docker compose down`/`up`, image rebuilds, and `up -d` recreating containers are routine and don't need confirmation.
- When committing, write a useful message; the user won't object to a real description even though their own messages are short.
