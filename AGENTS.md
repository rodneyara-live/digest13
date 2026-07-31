# Digest 13 — Agent Guide

## State

**Pipeline implemented in `src/`.** Single source of truth for design intent: `BLUEPRINT.md`. Read it before modifying the pipeline.

- LLM backend: **Groq** (model: `openai/gpt-oss-120b`) — free tier, no prepay required
- Env key: `GROQ_API_KEY`
- Model is a *reasoning* model: it spends tokens on chain-of-thought before answering, so `max_tokens` must be generous (relevance=300, paragraph=600, editorial review=1500) or it returns empty strings
- Groq free tier: **100K tokens/day** for `llama-3.3-70b-versatile` (pipeline volume), **200K tokens/day** for `openai/gpt-oss-120b` (editorial review). One daily run uses ~60-70K. `call_llm` retries on 429 only for transient rate limits; TPD exhaustion fails fast (no futile retries)

## Architecture (from BLUEPRINT.md)

- Python 3.10+ pipeline: RSS feeds → relevance scoring (1-5) → LLM dedup by event → quota-based selection → full-article fetch → paragraph generation → editorial review → HTML generation → `edge-tts` MP3 synthesis → MIME email via SMTP
- Selection quotas (`main.py`): Costa Rica min 3 / max 5, Geopolítica max 6, Tecnología max 5, total max 15 items (~10-12 min audio)
- Editorial review uses a separate reasoning model (`EDITORIAL_MODEL`, default `openai/gpt-oss-120b`) — gives it a distinct daily quota
- RSS sources: The Guardian, BBC, Al Jazeera, Delfino.cr, Semanario Universidad, Ars Technica
- Triggered via systemd `oneshot` service + `OnCalendar=*-*-* 07:00:00` timer with `Persistent=true`
- Local cache isolation: redirect all cache/temp dirs under `.cache/` (set `HF_HOME`, `XDG_CACHE_HOME`, `TORCH_HOME` at module init)
- GPU path (future): detect `cuda`, use `float16` or INT4 quantization for 4GB VRAM (NVIDIA Quadro T2000)

## Source files (current)

- `main.py` — orchestrator + `select_by_quota()`
- `web_searcher.py` — RSS aggregation (6 items/feed max)
- `relevance.py` — LLM scoring filter (PUNTAJE 1-5, reclassifies section) + `deduplicate_by_event()` (single LLM call groups same-event stories before selection)
- `article_fetcher.py` — `requests` + manual gzip/br decompression + `trafilatura` (Semanario needs this)
- `paragraph_gen.py` — HECHO+CONTEXTO+IMPLICACIÓN paragraph (max_tokens=600)
- `editorial_review.py` — second-pass review (max_tokens=1500, `EDITORIAL_MODEL`)
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
```

## Key style constraints

- LLM prompts (see BLUEPRINT.md) are exact — must be sent verbatim. They live in `relevance.py`, `paragraph_gen.py`, and `editorial_review.py`
- Each news item ends with its source attribution (`(Fuente: ...)`)
- Text cleaned via `text_cleaner.strip_markdown()` before TTS synthesis
- Temp files (MP3, HTML) deleted after successful email send
- HTML output must embed audio via `cid:audio_resumen_mp3` (attachment, not URL)
- All news sections: independent, self-contained items; no connective phrases between stories
- Supported voice default: `es-CR-MariaNeural`
