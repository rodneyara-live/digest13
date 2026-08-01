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

1. **`web_searcher.fetch_items()`** — polls 8 RSS feed URLs across 3 hardcoded sections (Mundo, Costa
   Rica, Tecnología), dedupes by title, caps at `MAX_PER_FEED=6` items/feed, and skips articles older
   than 48 hours (UTC). Returns `Item` dataclasses (section, title, source, url, summary, score, paragraph_md).
   Feeds are parsed concurrently (`FEED_WORKERS=8`), but `_parse_feed()` returns *every* eligible entry
   and the merge loop re-applies dedup and `MAX_PER_FEED` walking `FEEDS` in declared order — so when two
   feeds carry the same story the winner stays the one listed first, and the per-feed cap still counts only
   items that survive dedup. Don't move either back into the worker; that would make output depend on
   which thread finished first.
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
   don't remove this even if it looks redundant. `main.fetch_all_articles()` runs all 15 downloads
   concurrently (`ARTICLE_WORKERS=5`) into a `{url: text}` dict *before* the paragraph loop — at a 20s
   timeout each this is the run's slowest stretch and it costs no tokens. The paragraph loop stays serial
   on purpose: concurrent LLM calls pressure the free tier's RPM limit for no gain.
6. **`paragraph_gen.generate_paragraph()`** — one LLM call per article, producing a `### Title` +
   HECHO/CONTEXTO/IMPLICACIÓN paragraph. The model only writes the title text; a regex
   (`^###\s*\[?(.+?)\]?\s*$`) then injects the real `Item.url` into it as `### [título](url)`, tolerating
   whether the model wrapped its own title in brackets or not — this guarantees exactly one bracket pair
   and a real URL regardless of what the model did. Input truncated to 2500 chars, `max_tokens=800`.
   Banned phrases ("es importante", "genera debate", etc.) are enforced by the prompt.
7. **`editorial_review.review()`** — strict quality gate (single LLM call, `MAX_REVIEW_CHARS=24000`,
   `max_tokens=8000`, uses `EDITORIAL_MODEL`). The input cap must stay comfortably above a full digest
   (~12.5K chars for 15 items) and any trim must land on an item boundary via `_fit()`: an earlier
   8000-character *input* cap hid the last third of the report — the whole TECNOLOGÍA section — from the
   "last line of defense", and cut mid-URL, so the editor reported phantom defects (a sliced link reads as
   broken, the straddled item as a title with no paragraph) and rejected a digest that it approves in full.
   `max_tokens` is separately generous because the reasoning model spends ~4.3K tokens per call on the full
   digest and returned *empty* at 2000. Rejects the entire digest if it detects broken format
   (JSON, thinking text, bullet lists), empty paragraphs, celebrity gossip, fabricated data, or >2
   stories on the same event. On RECHAZADO, `main.py` aborts the email send and logs the failure.
   Returns `None` on APROBADO, otherwise a correction list. **Both verdicts must be matched through
   `_verdict()`**, which strips leading markdown/whitespace before comparing — the model routinely answers
   `**RECHAZADO:**` or `### APROBADO`, and a bare `startswith("RECHAZADO")` misses that and makes the gate
   fail *open*, mailing a digest the editor rejected (observed in the 2026-08-01 12:48 run). `main.py` must
   use `is_rejection()` rather than re-implementing the check. A third state matters: `is_gate_failure()` is
   true when the review call itself produced nothing (truncated or failed). That is not an approval — the
   digest ships unreviewed — so `main()` appends "SIN revisión editorial" to the run-log status rather than
   recording a clean OK.
8. **`html_generator.build_html()`** / **`text_cleaner.strip_markdown()`** / **`tts_engine.synthesize()`**
   — build the final HTML (audio embedded via `cid:audio_resumen_mp3`, not a URL) and the MP3 (via
   `edge-tts`, default voice `es-CR-MariaNeural`) in parallel-ish sequence; TTS runs on markdown stripped
   of formatting so it isn't read aloud.
9. **`email_sender.send()`** — assembles the MIME package (HTML body + MP3 attachment) and sends over
   SMTP (`timeout=30`). `main()` deletes the temp MP3/HTML files after a successful send.

### LLM layer (`llm.py`)

`call_llm(system_prompt, user_prompt, max_tokens, temperature, model=None)` wraps a module-level Groq
client (`_get_client()`, built once and reused). `model` defaults to `LLM_MODEL` if not passed explicitly.
**Three models, three independent daily quotas**, assigned per stage by how much that stage's quality
matters — see `BLUEPRINT.md`'s "Pipeline de Curación" table for the authoritative per-stage breakdown:

- `FILTER_MODEL` (default `llama-3.1-8b-instant`, non-reasoning, 500K tokens/day) — passed explicitly via
  `model=FILTER_MODEL` in `relevance.py` (stages 1-2). This is the highest-volume stage by far (one call
  per RSS item, ~44/day, ~65% of the run's tokens) and the cheapest judgment: scoring 1-5 against an
  explicit rubric. It lives on the 500K quota precisely so it can't cannibalize the paragraph budget.
- `LLM_MODEL` (default `llama-3.3-70b-versatile`, non-reasoning, 100K tokens/day) — the `call_llm` default,
  so only `paragraph_gen.py` (stage 5) uses it implicitly. Paragraph writing is what determines whether the
  digest reads well, so it gets the strongest model with ~7x headroom (~14K of 100K per run).
- `EDITORIAL_MODEL` (default `openai/gpt-oss-120b`, *reasoning*, 200K tokens/day) — passed explicitly via
  `model=EDITORIAL_MODEL` only in `editorial_review.py` (stage 6).

**Never set a reasoning model as `FILTER_MODEL`/`LLM_MODEL`.** Measured: a run with `gpt-oss-20b` as the
volume model spent 1,173 tokens/call vs 832 for `llama-3.1-8b-instant` on identical work (+41%), all of it
hidden chain-of-thought. If it's ever unavoidable, `reasoning_effort="low"` is the parameter that actually
suppresses that generation — `include_reasoning=False` only hides it from the response.

`EDITORIAL_MODEL` burns tokens on hidden chain-of-thought before emitting its answer, so its `max_tokens`
must stay generous or the response comes back empty/truncated — `llm.py` logs `⚠ TRUNCADO` when
`response.choices[0].finish_reason == "length"`, which is the reliable signal to recalibrate a limit
instead of guessing from output length. Current values: relevance=600, dedup=600, paragraph=800,
editorial review=8000. `LLM_MODEL` doesn't carry the same hidden-reasoning cost but keeps the same
generous caps anyway — headroom is cheap since `max_tokens` only bounds spend, it doesn't pre-allocate it.

Retries 3x on 429 with linear backoff (30s, 60s, 90s), except when the error text contains "tokens per
day" (TPD quota exhausted) — that triggers automatic fallback to a backup model. Which backup is a lookup
in `FALLBACK_CHAIN`, an explicit `{primary: backup}` dict built from config; with three primaries there's
no reliable way to infer the caller's quota from the shape of the `model` argument, which is what the
previous if-chain did. Self-mappings are filtered out, since `FILTER_MODEL` defaults to `VOLUME_FALLBACK`.
- `FILTER_MODEL` → `LLM_MODEL` — falls *up* on purpose: with no stage-1 model nothing gets approved and
  `main()` aborts, so spending paragraph headroom beats shipping nothing. This makes the volume chain a
  cycle (8b → 70b → 8b); `_first_available()`'s `seen` set is what terminates it.
- `LLM_MODEL` → `llama-3.1-8b-instant` (500K TPD, non-reasoning, 840 TPS)
- `EDITORIAL_MODEL` → `openai/gpt-oss-20b` (200K TPD)

Exhaustion is remembered for the rest of the process in `llm.py`'s `_exhausted` set, and announced once
rather than once per call — otherwise a degraded run wastes a round-trip per call rediscovering that the
primary is dead. When every model in a chain is exhausted, the call returns `None`.

There is deliberately **no local token budget**. An earlier `TOKEN_LIMIT`/`approx_tokens` gate in `main.py`
estimated spend as `chars // 4` starting from zero inside the paragraph loop, so it never counted the ~34K
already spent on relevance and never actually fired; a single global ceiling also doesn't correspond to
three independent per-model quotas. The TPD fallback chain handles real exhaustion, so don't reintroduce an
estimated gate — it can only skip news over a fictional number.

One full run uses ~52K combined across the three models (~34K relevance, ~14K paragraphs, ~1.5K dedup,
~3.5K editorial). Token usage is tracked per-model via `response.usage.total_tokens` (exposed by Groq),
accumulated in `llm.py`'s `_token_usage` dict, and written to `logs/digest13.log` after each run by
`main.py`'s `_write_run_log()` function — that log is the authoritative record of which model did what.

### Source selection is editorial, not technical

The `FEEDS` list in `web_searcher.py` is a deliberate editorial decision — **read BLUEPRINT.md's "Criterio
de selección de fuentes" before proposing any new source.** Costa Rica having only two feeds is intentional,
not a gap to fill: La Nación, El Observador, Monumental and others were evaluated and rejected on editorial
grounds despite working fine technically. The criterion excludes content engineered to generate division
rather than inform, in both political directions — which is also what the `SINDEU`/`fedes` rejection line in
`relevance.py`'s prompt actually implements (it filters union agitation content out of Semanario Universidad,
it is not a university-PR noise filter). Evaluate editorial line first, RSS/extraction second.

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
