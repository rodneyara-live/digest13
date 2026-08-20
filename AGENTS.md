# Digest 13 — Agent Guide

## State

**Pipeline implemented in `src/`.** Single source of truth for design intent: `BLUEPRINT.md`. Read it before modifying the pipeline.

- LLM backend: **Groq**, three models with independent daily quotas, assigned per stage by how much that stage's quality matters — see `BLUEPRINT.md` "Pipeline de Curación" table for the authoritative breakdown
  - `FILTER_MODEL` (default `allam-2-7b`, non-reasoning) — stages 1, 2 (relevance, dedup): the highest-volume, cheapest-judgment stages, ~44 calls/day
  - `LLM_MODEL` (default `qwen/qwen3.6-27b`, reasoning) — stage 5 (paragraph) only: the stage that defines the digest's quality
  - `EDITORIAL_MODEL` (default `openai/gpt-oss-120b`, *reasoning*) — stage 6 (editorial review) only
- Env key: `GROQ_API_KEY`; `call_llm(..., model=...)` picks the model per call, defaults to `LLM_MODEL`
- **Fallback chain** (`FALLBACK_CHAIN` in `llm.py`, an explicit dict — not inferred from the shape of the `model` argument): when a model exhausts its TPD, `call_llm()` auto-switches and **remembers it for the rest of the run** (`_exhausted`), instead of re-probing the dead model on every later call
  - `FILTER_MODEL` → `LLM_MODEL` (falls *up*: with no stage-1 model nothing is approved and the run aborts, so burning paragraph headroom beats shipping nothing)
  - `LLM_MODEL` → `allam-2-7b` (non-reasoning) — falls back to volume fallback
  - `EDITORIAL_MODEL` → `openai/gpt-oss-20b` (200K TPD)
  Configurable via `FILTER_MODEL` / `VOLUME_FALLBACK` / `REASONING_FALLBACK` in `.env`
- **Never put a reasoning model in `FILTER_MODEL`:** measured +41% tokens per call for identical work (`gpt-oss-20b` 1,173 vs `allam-2-7b` 832) from hidden chain-of-thought. If unavoidable, `reasoning_effort="low"` is what actually reduces generation; `include_reasoning=False` only hides it from the response.
- `EDITORIAL_MODEL` is a reasoning model: it spends tokens on hidden chain-of-thought before answering, so its `max_tokens` must stay generous or it returns empty/truncated text — `llm.py` logs `⚠ TRUNCADO` when `finish_reason == "length"` to catch this without guessing. Current values: relevance=600, dedup=600, paragraph=800, editorial review=8000 — `LLM_MODEL` doesn't need the headroom but keeps the same generous caps for margin.
- One daily run uses ~52K combined (~34K relevance, ~14K paragraphs, ~1.5K dedup, ~3.5K editorial). `call_llm` retries on 429 only for transient rate limits; TPD exhaustion auto-switches to fallback model (no futile retries on exhausted model)
- **Cross-day dedup via SQLite** (`seen_store.py`, DB at `.cache/seen.sqlite3`, gitignored): the 48h RSS window re-introduces yesterday's articles, so `main.py` blocks items already **sent** in a previous digest before the relevance filter (saves FILTER_MODEL tokens too). Key = normalized URL (scheme http/https, `www.`, case and path unified; query/fragment dropped) OR `(source, title_key)` (normalized title) for the same story re-published under a new URL. Only delivered items block (`mark_sent` runs after a successful send); everything fetched is recorded (`note_seen`) for audit but never blocks, so a story that missed the quota or a failed download can still appear another day. Rows pruned after 30 days. Intra-run dedup (LLM `deduplicate_by_event` + keyword Jaccard) is unchanged.

## Architecture (from BLUEPRINT.md)

- Python 3.10+ pipeline: RSS feeds → SQLite seen-store blocks already-sent articles → relevance scoring (1-5) → LLM dedup by event → quota-based selection (with a second, deterministic keyword-similarity dedup) → full-article fetch → paragraph generation → editorial review → HTML generation → `edge-tts` MP3 synthesis → MIME email via SMTP
- Selection quotas (`main.py`): Costa Rica min 3 / max 5, Mundo max 6, Tecnología max 5, total max 15 items (~10-12 min audio); `_is_duplicate()` skips candidates with ≥0.65 keyword-Jaccard similarity to an already-selected item
- Editorial review uses a separate reasoning model (`EDITORIAL_MODEL`, default `openai/gpt-oss-120b`) — gives it a distinct daily quota
- RSS sources: The Guardian, BBC, Al Jazeera, Delfino.cr, Semanario Universidad, Ars Technica
- **Do not propose new sources without reading BLUEPRINT.md's "Criterio de selección de fuentes".** The feed list is a deliberate editorial decision; Costa Rica having only 2 feeds is intentional. La Nación, El Observador, Monumental and CRHoy were already evaluated and rejected. The criterion filters content engineered to generate division rather than inform — in both political directions — and is what the `SINDEU`/`fedes` rejection line in `relevance.py` actually implements
- Triggered via systemd `oneshot` service + `OnCalendar=*-*-* 07:00:00` timer with `Persistent=true`
- Failure alerting: `OnFailure=digest13-notify.service` triggers `on-failure.sh` which logs to `logs/failures.log`
- `main.py` exits with `sys.exit(1)` on critical failures (empty filter, fewer than `MIN_ITEMS_FOR_DIGEST`
  (5) paragraphs generated — not just zero)
- Error logging: `article_fetcher.py` and `web_searcher.py` log exception type and message on failures
- Token logging: `llm.py` tracks tokens per model; `main.py` writes summary to `logs/digest13.log` after each run
- Run log: `logs/digest13.log` accumulates a summary of each execution (items, tokens, status) — gitignored
- Local cache isolation: redirect all cache/temp dirs under `.cache/` (set `HF_HOME`, `XDG_CACHE_HOME`, `TORCH_HOME` at module init)
- GPU path (future): detect `cuda`, use `float16` or INT4 quantization for 4GB VRAM (NVIDIA Quadro T2000)

## Source files (current)

- `main.py` — orchestrator + `select_by_quota()`
- `web_searcher.py` — RSS aggregation (6 items/feed max, articles older than 48h UTC are skipped)
- `relevance.py` — LLM scoring filter (PUNTAJE 1-5, reclassifies section) + `deduplicate_by_event()` (single LLM call groups same-event stories before selection); unparseable answers are logged as `MALFORMADO`, never silently treated as `RECHAZADO`
- `article_fetcher.py` — `requests` + manual gzip/br decompression + `trafilatura` (Semanario needs this)
- `paragraph_gen.py` — HECHO+CONTEXTO+IMPLICACIÓN paragraph (max_tokens=2500); regex injects the real `Item.url` into the title, tolerating whether or not the model wrapped it in brackets itself
- `editorial_review.py` — strict quality gate (`MAX_REVIEW_CHARS=24000`, max_tokens=8000, `EDITORIAL_MODEL`); RECHAZADO stops the pipeline. Trim only on item boundaries (`_fit()`) and match verdicts via `_verdict()`/`is_rejection()` — a raw char cut invents defects, a bare `startswith` leaves the gate open
- `llm.py` — Groq client, retries on transient 429 only, `model` param per call
- `num2words.py` — numbers → Spanish words (`int_to_words`, `number_to_words`, `numbers_to_words`, CLI worker); wired into `text_cleaner.strip_markdown()` (TTS only, HTML untouched)
- `seen_store.py` — SQLite memory of delivered articles (`mark_sent`/`is_blocked`/`note_seen`/`prune`); see the "Cross-day dedup" bullet in State
- `html_generator.py`, `text_cleaner.py`, `tts_engine.py`, `email_sender.py` — output stage

## Dependencies

- `groq`, `edge-tts`, `python-dotenv`, `markdown`, `feedparser`, `trafilatura`, `requests`, `brotli`

## Setup

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env  # fill in GROQ_API_KEY, SMTP_*, EMAIL_*, TTS_VOICE
```

`.env` is required at project root — never commit it.

## Testing / CI / Lint

None configured. Manual runner: `venv/bin/python tests/test_num2words.py` and `venv/bin/python tests/test_seen_store.py` (pure-local asserts, no API calls). Needs proper CI/test setup as the project is built.

## .gitignore must cover

```
venv/
.cache/
.env
__pycache__/
*.mp3
*.html
debug_news.txt
logs/
```

## Key style constraints

- LLM prompts (see BLUEPRINT.md) are exact — must be sent verbatim. They live in `relevance.py`, `paragraph_gen.py`, and `editorial_review.py`
- Each news item title is a hyperlink to the original article (`### [Título](url)`) — Python guarantees exactly one bracket pair regardless of whether the model echoed brackets in its own output
- Text cleaned via `text_cleaner.strip_markdown()` before TTS synthesis; numbers are converted to letters via `num2words.py` (`₡2.300.500` → `dos millones trescientos mil quinientos colones`, `29,18%` → `veintinueve coma dieciocho por ciento`). Convention: `.`/space = thousands, `,` = decimal; pure digit runs (`4000000`) group from the right. Hours (`7:00`), dates (`07/08/2026`) and tokens like `PM2.5`/`4G` are left untouched
- Temp files (MP3, HTML) deleted after successful email send
- HTML output must embed audio via `cid:audio_resumen_mp3` (attachment, not URL)
- All news sections: independent, self-contained items; no connective phrases between stories
- Supported voice default: `es-CR-MariaNeural`
