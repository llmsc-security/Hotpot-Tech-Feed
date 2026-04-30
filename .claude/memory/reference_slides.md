---
name: Slide deck source of truth
description: docs/slides.pptx is generated; edit docs/build_slides.py and re-run, don't hand-edit the .pptx.
type: reference
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
- `docs/slides.pptx` — rendered 16:9 deck (8 slides: title + 4 tech + 2 tutorial + closing). Built with `python-pptx`.
- `docs/build_slides.py` — generator. Re-run with `python3 docs/build_slides.py` after any change.
- `docs/slides.md` — Marp-flavored markdown source. Useful for HTML/PDF rendering (`marp docs/slides.md`), but the PPTX path doesn't go through Marp because Marp requires a chromium binary.
- python-pptx is installed user-wide via `pip install --user --break-system-packages python-pptx` (system pip is PEP 668 managed on this host).
- Never commit hand-edits to `slides.pptx` directly — the next regen would clobber them. Edit `build_slides.py` (or `slides.md` for markdown deliverables) instead.
