# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Digest 13 is a single-run Python pipeline (`src/main.py`) that: pulls RSS headlines, scores them for
relevance with an LLM, selects a quota-balanced subset, fetches full article text, generates a structured
paragraph per item, runs an editorial review pass, builds an HTML report with embedded audio, synthesizes
TTS narration, and emails the package via SMTP. It runs unattended once a day via a systemd timer — there
is no server process and no web UI.

**`BLUEPRINT.md` is the source of truth for design intent** (exact prompts, HTML template, systemd units).
Read it before changing pipeline behavior — the prose here summarizes it but BLUEPRINT.md has the verbatim
text that must be reproduced exactly.

## Commands

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY, SMTP_*, EMAIL_*, TTS_VOICE
python src/main.py     # run the full pipeline once
```

No test suite, linter, or CI is configured. `src/main.py` runs its imports as top-level modules (`from
config import ...`, not `from src.config import ...`), so run it from inside `src/` context via
`python src/main.py` from the project root — do not add package-relative imports.

## Architecture

The pipeline is a strict linear sequence, each stage in its own module, orchestrated by `main()` in
[src/main.py](src/main.py):

1. **`web_searcher.fetch_items()`** — polls 6 RSS feeds across 3 hardcoded sections (Geopolítica, Costa
   Rica, Tecnología), dedupes by title, caps at `MAX_PER_FEED=6` items/feed. Returns `Item` dataclasses
   (section, title, source, url, summary, score, paragraph_md).
2. **`relevance.filter_items()`** — one LLM call per item. The model scores 1-5, may RECHAZAR (reject),
   and may reassign the item's section. Items scoring <2 or marked RECHAZAR are dropped. The rejection
   criteria list (sports, pseudoscience, anti-vax, university PR, etc.) lives in the prompt itself —
   changes to what gets filtered belong there, not in Python logic.
3. **`main.select_by_quota()`** — pure selection logic, no LLM. Two passes: first forces the Costa Rica
   minimum (3), then fills remaining slots by global score rank respecting each section's max
   (`SECTION_QUOTAS`), capped at `MAX_TOTAL=15` items total.
4. **`article_fetcher.fetch_full_text()`** — downloads each selected article with `requests` (browser
   headers, `Accept-Encoding: gzip, deflate, br`) and extracts text with `trafilatura`. Semanario
   Universidad's server returns gzip that `trafilatura`/`requests` won't auto-decompress, so there's
   manual decompression — don't remove it even if it looks redundant.
5. **`paragraph_gen.generate_paragraph()`** — one LLM call per article, producing a `### Title` +
   HECHO/CONTEXTO/IMPLICACIÓN paragraph. Title is a hyperlink to the original article. Input truncated to 2500 chars,
   `max_tokens=800`. Banned phrases ("es importante", "genera debate", etc.) are enforced by the prompt.
6. **`editorial_review.review()`** — single LLM call over the entire assembled digest (max 8000 chars,
   `max_tokens=1500`) checking structure and banned-phrase compliance. Returns `None`/empty on APROBADO,
   otherwise a correction list that is currently only logged, not auto-applied.
7. **`html_generator.build_html()`** / **`text_cleaner.strip_markdown()`** / **`tts_engine.synthesize()`**
   — build the final HTML (audio embedded via `cid:audio_resumen_mp3`, not a URL) and the MP3 (via
   `edge-tts`, default voice `es-CR-MariaNeural`) in parallel-ish sequence; TTS runs on markdown stripped
   of formatting so it isn't read aloud.
8. **`email_sender.send()`** — assembles the MIME package (HTML body + MP3 attachment) and sends over
   SMTP. `main()` deletes the temp MP3/HTML files after a successful send.

### LLM layer (`llm.py`)

Single `call_llm(system_prompt, user_prompt, max_tokens, temperature)` wrapper around the Groq client
(model from `LLM_MODEL` env var, default `openai/gpt-oss-120b`). This is a *reasoning* model — it burns
tokens on hidden chain-of-thought before emitting the answer, so every call site needs a generous
`max_tokens` (300/600/1500 for relevance/paragraph/review respectively) or Groq returns an empty string.
Retries 3x on 429 with linear backoff (30s, 60s, 90s). Groq free tier is 200K tokens/day; one full run is
~60-70K, and `main.py` tracks an approximate running token count (`TOKEN_LIMIT=60_000`) to skip remaining
articles/the review pass if the budget looks exhausted mid-run.

### Config and caching (`config.py`)

Loads `.env` from `PROJECT_ROOT` (two levels up from `config.py`, i.e. repo root) via `python-dotenv`.
`SMTP_*` and `EMAIL_*` vars are required (`os.environ[...]`, no default) — the process will raise on
import if `.env` is missing them. Also redirects `HF_HOME`/`XDG_CACHE_HOME`/`TORCH_HOME` under
`.cache/` at import time, before any other import that might touch those — this keeps any future
local-model/torch usage from writing to `~/.cache`. Preserve that ordering if you add imports to
`main.py`.

### Data flow shape

Everything downstream of RSS fetch operates on the same mutable `Item` dataclass
([src/web_searcher.py](src/web_searcher.py)) — `relevance.py` mutates `.score`/`.section` in place,
`paragraph_gen.py` sets `.paragraph_md`. There's no intermediate persistence between stages within a run
(`debug_news.txt` is written once, post-assembly, purely for debugging and is gitignored).

## Key constraints when touching pipeline code

- LLM prompts in `relevance.py`, `paragraph_gen.py`, `editorial_review.py` must match BLUEPRINT.md
  verbatim — they are tuned/exact, not illustrative.
- Every news item title must be a hyperlink to the original article (`### [Título](url)`); sections are independent/self-contained blocks
  with no connective transitions between stories.
- HTML output embeds audio as `cid:audio_resumen_mp3` (MIME attachment reference), never a file:// or
  http URL.
- Section quotas and `MAX_TOTAL=15` target ~10-12 minutes of synthesized audio — don't casually raise
  these without checking that assumption still holds.
- Temp MP3/HTML files are deleted only after a successful send; if you change error handling around
  `email_sender.send()`, keep that ordering so failures leave artifacts for debugging.
