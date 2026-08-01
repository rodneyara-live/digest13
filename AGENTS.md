# Digest 13 — Agent Guide

## State

**Pipeline implemented in `src/`.** Single source of truth for design intent: `BLUEPRINT.md`. Read it before modifying the pipeline.

- LLM backend: **Groq**, two models with two independent daily quotas — see `BLUEPRINT.md` "Pipeline de Curación" table for the authoritative breakdown
  - `LLM_MODEL` (default `llama-3.3-70b-versatile`, non-reasoning, **100K tokens/day**) — stages 1, 2, 5 (relevance, dedup, paragraph)
  - `EDITORIAL_MODEL` (default `openai/gpt-oss-120b`, *reasoning*, **200K tokens/day**) — stage 6 (editorial review) only
- Env key: `GROQ_API_KEY`; `call_llm(..., model=...)` picks the model per call, defaults to `LLM_MODEL`
- **Fallback chain:** when a model exhausts its TPD, `call_llm()` auto-switches to fallback:
  - Volume: `llama-3.3-70b-versatile` → `llama-3.1-8b-instant` (500K TPD, non-reasoning)
  - Reasoning: `openai/gpt-oss-120b` → `openai/gpt-oss-20b` (200K TPD)
  Configurable via `VOLUME_FALLBACK` / `REASONING_FALLBACK` in `.env`
- `EDITORIAL_MODEL` is a reasoning model: it spends tokens on hidden chain-of-thought before answering, so its `max_tokens` must stay generous or it returns empty/truncated text — `llm.py` logs `⚠ TRUNCADO` when `finish_reason == "length"` to catch this without guessing. Current values: relevance=600, dedup=600, paragraph=800, editorial review=1500 — `LLM_MODEL` doesn't need the headroom but keeps the same generous caps for margin.
- One daily run uses ~60-70K combined. `call_llm` retries on 429 only for transient rate limits; TPD exhaustion auto-switches to fallback model (no futile retries on exhausted model)

## Architecture (from BLUEPRINT.md)

- Python 3.10+ pipeline: RSS feeds → relevance scoring (1-5) → LLM dedup by event → quota-based selection (with a second, deterministic keyword-similarity dedup) → full-article fetch → paragraph generation → editorial review → HTML generation → `edge-tts` MP3 synthesis → MIME email via SMTP
- Selection quotas (`main.py`): Costa Rica min 3 / max 5, Geopolítica max 6, Tecnología max 5, total max 15 items (~10-12 min audio); `_is_duplicate()` skips candidates with ≥0.65 keyword-Jaccard similarity to an already-selected item
- Editorial review uses a separate reasoning model (`EDITORIAL_MODEL`, default `openai/gpt-oss-120b`) — gives it a distinct daily quota
- RSS sources: The Guardian, BBC, Al Jazeera, Delfino.cr, Semanario Universidad, Ars Technica
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
- `paragraph_gen.py` — HECHO+CONTEXTO+IMPLICACIÓN paragraph (max_tokens=800); regex injects the real `Item.url` into the title, tolerating whether or not the model wrapped it in brackets itself
- `editorial_review.py` — strict quality gate (max_tokens=1500, `EDITORIAL_MODEL`); RECHAZADO stops the pipeline
- `llm.py` — Groq client, retries on transient 429 only, `model` param per call
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

None configured. These need to be set up as the project is built.

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
- Text cleaned via `text_cleaner.strip_markdown()` before TTS synthesis; colones (`₡2.300.500`) become `2300500 colones` (thousands dots removed, symbol → word after number)
- Temp files (MP3, HTML) deleted after successful email send
- HTML output must embed audio via `cid:audio_resumen_mp3` (attachment, not URL)
- All news sections: independent, self-contained items; no connective phrases between stories
- Supported voice default: `es-CR-MariaNeural`
