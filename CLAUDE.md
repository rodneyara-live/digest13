# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Digest 13 is a single-run Python pipeline (`src/main.py`) that: pulls RSS headlines, scores them for
relevance with an LLM, deduplicates same-event stories, selects a quota-balanced subset, fetches full
article text, generates a structured paragraph per item, runs an editorial review pass, builds an HTML
report with embedded audio, synthesizes TTS narration, and emails the package via SMTP. It runs unattended
once a day via a systemd timer — there is no server process and no web UI.

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
   Rica, Tecnología), dedupes by title, caps at `MAX_PER_FEED=6` items/feed, and skips articles older
   than 48 hours (UTC). Returns `Item` dataclasses (section, title, source, url, summary, score, paragraph_md).
2. **`relevance.filter_items()`** — one LLM call per item. The model scores 1-5, may RECHAZAR (reject),
   and may reassign the item's section. Items scoring <2 or marked RECHAZAR are dropped. The rejection
   criteria list (sports, pseudoscience, anti-vax, university PR, etc.) lives in the prompt itself —
   changes to what gets filtered belong there, not in Python logic. `_parse_action()`/`_parse_score()`
   return `None` (not a default reject) when the model's answer doesn't contain a parseable
   `ACCIÓN:`/`PUNTAJE:` line — this is logged as `MALFORMADO`, distinct from a genuine `RECHAZADO`, so a
   model that ignores the expected format (e.g. an unfamiliar fallback) doesn't silently masquerade as a
   slow news day.
3. **`relevance.deduplicate_by_event()`** — one LLM call over the top-20 approved items (by score) asking
   the model to group items covering the *same* underlying event (e.g. the same story on Guardian + BBC).
   Keeps the highest-scored item per group, drops the rest. Returns the input unchanged if there are fewer
   than 4 items, if the call fails, or if no groups are found.
4. **`main.select_by_quota()`** — pure selection logic, no LLM. Two passes: first forces the Costa Rica
   minimum (3), then fills remaining slots by global score rank respecting each section's max
   (`SECTION_QUOTAS`), capped at `MAX_TOTAL=15` items total. Both passes also skip a candidate via
   `_is_duplicate()` if it has ≥0.65 keyword-Jaccard similarity to an item already selected — a second,
   deterministic dedup layer that catches near-duplicates the LLM step above didn't group.
5. **`article_fetcher.fetch_full_text()`** — downloads each selected article with `requests` (browser
   headers, `Accept-Encoding: gzip, deflate, br`) and extracts text with `trafilatura`, decompressing the
   response with `_decompress()` (gzip/zlib/brotli, falls back to raw bytes) before decoding. Semanario
   Universidad's server returns compressed bytes that `requests` won't auto-decompress on its own, so
   don't remove this even if it looks redundant.
6. **`paragraph_gen.generate_paragraph()`** — one LLM call per article, producing a `### Title` +
   HECHO/CONTEXTO/IMPLICACIÓN paragraph. The model only writes the title text; a regex
   (`^###\s*\[?(.+?)\]?\s*$`) then injects the real `Item.url` into it as `### [título](url)`, tolerating
   whether the model wrapped its own title in brackets or not — this guarantees exactly one bracket pair
   and a real URL regardless of what the model did. Input truncated to 2500 chars, `max_tokens=800`.
   Banned phrases ("es importante", "genera debate", etc.) are enforced by the prompt.
7. **`editorial_review.review()`** — strict quality gate (single LLM call, max 8000 chars,
   `max_tokens=1500`, uses `EDITORIAL_MODEL`). Rejects the entire digest if it detects broken format
   (JSON, thinking text, bullet lists), empty paragraphs, celebrity gossip, fabricated data, or >2
   stories on the same event. On RECHAZADO, `main.py` aborts the email send and logs the failure.
   Returns `None` on APROBADO, otherwise a correction list.
8. **`html_generator.build_html()`** / **`text_cleaner.strip_markdown()`** / **`tts_engine.synthesize()`**
   — build the final HTML (audio embedded via `cid:audio_resumen_mp3`, not a URL) and the MP3 (via
   `edge-tts`, default voice `es-CR-MariaNeural`) in parallel-ish sequence; TTS runs on markdown stripped
   of formatting so it isn't read aloud.
9. **`email_sender.send()`** — assembles the MIME package (HTML body + MP3 attachment) and sends over
   SMTP (`timeout=30`). `main()` deletes the temp MP3/HTML files after a successful send.

### LLM layer (`llm.py`)

`call_llm(system_prompt, user_prompt, max_tokens, temperature, model=None)` wraps a module-level Groq
client (`_get_client()`, built once and reused). `model` defaults to `LLM_MODEL` if not passed explicitly.
**Two models, two independent daily quotas** — see `BLUEPRINT.md`'s "Pipeline de Curación" table for the
authoritative per-stage breakdown:

- `LLM_MODEL` (default `llama-3.3-70b-versatile`, non-reasoning, 100K tokens/day) — used implicitly by
  `relevance.py` (stages 1-2) and `paragraph_gen.py` (stage 5).
- `EDITORIAL_MODEL` (default `openai/gpt-oss-120b`, *reasoning*, 200K tokens/day) — passed explicitly via
  `model=EDITORIAL_MODEL` only in `editorial_review.py` (stage 6).

`EDITORIAL_MODEL` burns tokens on hidden chain-of-thought before emitting its answer, so its `max_tokens`
must stay generous or the response comes back empty/truncated — `llm.py` logs `⚠ TRUNCADO` when
`response.choices[0].finish_reason == "length"`, which is the reliable signal to recalibrate a limit
instead of guessing from output length. Current values: relevance=600, dedup=600, paragraph=800,
editorial review=1500. `LLM_MODEL` doesn't carry the same hidden-reasoning cost but keeps the same
generous caps anyway — headroom is cheap since `max_tokens` only bounds spend, it doesn't pre-allocate it.

Retries 3x on 429 with linear backoff (30s, 60s, 90s), except when the error text contains "tokens per
day" (TPD quota exhausted) — that triggers automatic fallback to a backup model:
- Volume: `llama-3.3-70b-versatile` → `llama-3.1-8b-instant` (500K TPD, non-reasoning, 840 TPS)
- Reasoning: `openai/gpt-oss-120b` → `openai/gpt-oss-20b` (200K TPD)

If both models in a chain are exhausted, the call returns `None`. One full run uses
~60-70K combined across both models. Token usage is tracked per-model via `response.usage.total_tokens`
(exposed by Groq), accumulated in `llm.py`'s `_token_usage` dict, and written to `logs/digest13.log`
after each run by `main.py`'s `_write_run_log()` function.

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
- Every news item title must be a hyperlink to the original article (`### [Título](url)`), with the URL
  always injected in Python from `Item.url` — never trust the model to write it. Sections are
  independent/self-contained blocks with no connective transitions between stories.
- HTML output embeds audio as `cid:audio_resumen_mp3` (MIME attachment reference), never a file:// or
  http URL.
- Section quotas and `MAX_TOTAL=15` target ~10-12 minutes of synthesized audio — don't casually raise
  these without checking that assumption still holds.
- Temp MP3/HTML files are deleted only after a successful send; if you change error handling around
  `email_sender.send()`, keep that ordering so failures leave artifacts for debugging.
- `main.py` aborts (`sys.exit(1)`, no email sent) if fewer than `MIN_ITEMS_FOR_DIGEST` (5) paragraphs
  are generated — not just zero. A single-digit digest is treated as a degenerate run (most likely an
  LLM not following the expected format) rather than a real slow news day, since nothing downstream
  (editorial review's criteria are about *too many* same-event stories, not too few items) catches that
  case otherwise.
