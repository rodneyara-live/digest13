# Digest 13 — Agent Guide

## State

**Blueprint-only repo.** No implementation exists yet. Single source of truth: `BLUEPRINT.md`. Before coding, read it thoroughly.

## Architecture (from BLUEPRINT.md)

- Python 3.10+ pipeline: LLM query (Google AI Studio / Gemini) → HTML generation → `edge-tts` MP3 synthesis → MIME email via SMTP
- Triggered via systemd `oneshot` service + `OnCalendar=*-*-* 07:00:00` timer with `Persistent=true`
- Local cache isolation: redirect all cache/temp dirs under `.cache/` (set `HF_HOME`, `XDG_CACHE_HOME`, `TORCH_HOME` at module init)
- GPU path (future): detect `cuda`, use `float16` or INT4 quantization for 4GB VRAM (NVIDIA Quadro T2000)

## Dependencies

- `google-genai`, `edge-tts`, `python-dotenv`

## Setup

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env  # fill in GEMINI_API_KEY, SMTP_*, EMAIL_*, TTS_VOICE
```

`.env` is required at project root — never commit it.

## Testing / CI / Lint

None configured. These need to be set up as the project is built.

## .gitignore must cover

```
venv/
.cache/
.env
*.mp3
*.html
```

## Key style constraints

- LLM prompt (see BLUEPRINT.md) is exact — must be sent verbatim to Gemini
- HTML output must embed audio via `cid:audio_resumen_mp3` (attachment, not URL)
- All news sections: independent, self-contained items; no connective phrases between stories
- Supported voice default: `es-CR-MariaNeural`
