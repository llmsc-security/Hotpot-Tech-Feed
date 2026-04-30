---
name: Host & LLM endpoint
description: User runs Hotpot on a 256-core Linux host backed by a self-hosted Qwen3.5 OpenAI-compatible endpoint at api.ai2wj.com.
type: user
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
- Host: Linux 6.8 x86_64, **256 logical CPUs** (`nproc` confirmed). Naive `cpu_count // 2` defaults explode on this box — see `project_hotpot_deploy.md` for the cap.
- LLM: self-hosted Qwen3.5 served via vLLM at `https://api.ai2wj.com/v1/` (OpenAI-compatible). Auth key is whatever you set in `.env` (`OPENAI_API_KEY`); the user has been using `"111"` as a placeholder during dev.
- Available model name: `Qwen/Qwen3.5-397B-A17B`. Earlier values like `qwen3.6` were placeholders that don't exist on this endpoint and 404 the request.
- Endpoint can return transient `502 Bad Gateway`s under load; the OpenAI SDK retries automatically (don't stack additional retry layers).
