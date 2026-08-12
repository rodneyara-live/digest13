import asyncio
import re
import socket
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from config import PROJECT_ROOT, EMAIL_TO
from web_searcher import fetch_items
from relevance import filter_items, deduplicate_by_event
from article_fetcher import fetch_full_text
from paragraph_gen import generate_paragraph
from editorial_review import review, is_rejection, is_gate_failure
from html_generator import build_html
from text_cleaner import strip_markdown
from tts_engine import synthesize
from email_sender import send
from llm import get_token_usage
from seen_store import SeenStore

DATE_STAMP = date.today().strftime("%Y.%m.%d")
MP3_FILENAME = f"digest13.{DATE_STAMP}.mp3"
HTML_FILENAME = f"digest13.{DATE_STAMP}.html"
SEEN_DB = PROJECT_ROOT / ".cache" / "seen.sqlite3"
SEEN_RETENTION_DAYS = 30

SECTION_ORDER = [
    "MUNDO",
    "COSTA RICA",
    "TECNOLOGÍA",
]

SECTION_QUOTAS: dict[str, dict] = {
    "MUNDO": {"max": 6},
    "COSTA RICA": {"min": 3, "max": 5},
    "TECNOLOGÍA": {"max": 5},
}
MAX_TOTAL = 15
ARTICLE_WORKERS = 5  # article downloads are network-bound; the LLM calls stay serial
MIN_ITEMS_FOR_DIGEST = 5  # below this, treat the run as degenerate (e.g. a fallback model ignoring
                          # the expected PUNTAJE/ACCIÓN format) rather than a genuinely slow news day

LOG_DIR = PROJECT_ROOT / "logs"
RUN_LOG = LOG_DIR / "digest13.log"

CONNECTIVITY_RETRIES = 3
CONNECTIVITY_DELAY = 600  # 10 minutes


def _check_internet() -> bool:
    """Return True if DNS resolution and a TCP handshake to Groq succeed."""
    for host in ("api.groq.com", "www.theguardian.com"):
        try:
            socket.create_connection((host, 443), timeout=10)
        except OSError:
            return False
    return True


def _ensure_connectivity() -> None:
    """Block until the network is usable, retrying up to CONNECTIVITY_RETRIES times."""
    for attempt in range(1, CONNECTIVITY_RETRIES + 1):
        if _check_internet():
            if attempt > 1:
                print(f"  Conexión restaurada en el intento {attempt}")
            return
        if attempt < CONNECTIVITY_RETRIES:
            print(f"  Sin conexión (intento {attempt}/{CONNECTIVITY_RETRIES}). Reintentando en {CONNECTIVITY_DELAY // 60} minutos...")
            time.sleep(CONNECTIVITY_DELAY)
    print("ERROR: Sin conexión después de varios reintentos")
    _write_run_log("FALLO — Sin conexión a internet", {})
    sys.exit(1)


def _write_run_log(status: str, stats: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"=== {timestamp} ==="]
    lines.append(f"Items RSS: {stats.get('rss', 0)} | Ya enviados (descartados): {stats.get('blocked', 0)} | Aprobados: {stats.get('approved', 0)} | Seleccionados: {stats.get('selected', 0)}")
    lines.append(f"Artículos descargados: {stats.get('downloaded', 0)} | Párrafos generados: {stats.get('paragraphs', 0)}")
    token_usage = get_token_usage()
    if token_usage:
        lines.append("Tokens:")
        total_tokens = 0
        for model, data in token_usage.items():
            lines.append(f"  {model}: {data['total']:,} tokens ({data['calls']} llamadas)")
            total_tokens += data["total"]
        lines.append(f"  Total: {total_tokens:,} tokens")
    lines.append(f"Estado: {status}")
    lines.append("")
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _section_rank(section: str) -> int:
    try:
        return SECTION_ORDER.index(section)
    except ValueError:
        return 99


_ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")
_STOPWORDS = {
    "a", "al", "ante", "bajo", "como", "con", "contra", "de", "del", "desde",
    "donde", "durante", "e", "el", "en", "entre", "era", "es", "esta", "estas",
    "este", "esto", "fue", "ha", "hacia", "han", "hasta", "la", "las", "le",
    "lo", "los", "mas", "mediante", "mientras", "o", "para", "por", "que", "se",
    "según", "sin", "sobre", "su", "sus", "tras", "un", "una", "y", "ya",
    "and", "are", "at", "be", "been", "by", "for", "from", "has", "have", "he",
    "in", "is", "it", "not", "of", "on", "says", "said", "that", "the", "their",
    "they", "this", "to", "was", "were", "with", "will", "after", "over",
}


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower().translate(_ACCENTS))
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _similarity(a: str, b: str) -> float:
    ka, kb = _keywords(a), _keywords(b)
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / len(ka | kb)


def _is_duplicate(item, selected: list) -> bool:
    text = f"{item.title} {item.summary[:300]}"
    for sel in selected:
        other = f"{sel.title} {sel.summary[:300]}"
        if _similarity(text, other) >= 0.65:
            return True
    return False


def select_by_quota(items: list) -> list:
    by_section: dict[str, list] = defaultdict(list)
    for item in items:
        by_section[item.section].append(item)

    for sec in by_section:
        by_section[sec].sort(key=lambda i: (-i.score, i.title))

    selected: list = []
    counts: dict[str, int] = defaultdict(int)

    # Pass 1: force minimum for Costa Rica (distinct stories)
    cr_key = "COSTA RICA"
    cr_min = SECTION_QUOTAS.get(cr_key, {}).get("min", 0)
    for item in by_section.get(cr_key, []):
        if counts[cr_key] >= cr_min:
            break
        if _is_duplicate(item, selected):
            continue
        selected.append(item)
        counts[cr_key] += 1

    # Pass 2: global ranking by score, respecting caps and skipping duplicates
    remaining = sorted(
        [i for i in items if i not in selected],
        key=lambda i: (-i.score, i.title),
    )
    for item in remaining:
        if len(selected) >= MAX_TOTAL:
            break
        sec = item.section
        sec_max = SECTION_QUOTAS.get(sec, {}).get("max", 999)
        if counts[sec] >= sec_max:
            continue
        if _is_duplicate(item, selected):
            continue
        selected.append(item)
        counts[sec] += 1

    selected.sort(key=lambda i: (_section_rank(i.section), -i.score, i.title))
    return selected


def fetch_all_articles(items: list) -> dict[str, str]:
    """Download every selected article at once, keyed by URL. Downloads dominate
    the run's wall-clock (20s timeout each, serial before this) and cost nothing."""
    texts: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=ARTICLE_WORKERS) as pool:
        futures = {pool.submit(fetch_full_text, item.url): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                text = future.result()
            except Exception as e:
                print(f"  ERROR [{type(e).__name__}]: {e} — {item.url[:60]}")
                continue
            if text:
                texts[item.url] = text
    return texts


def assemble(items: list) -> str:
    sections: dict[str, list[str]] = {}
    for item in items:
        sections.setdefault(item.section, []).append(item.paragraph_md)

    parts = []
    for section in SECTION_ORDER:
        paras = sections.get(section)
        if paras:
            parts.append(f"## {section}")
            parts.extend(paras)
            parts.append("")
    return "\n".join(parts).strip()


def main() -> None:
    stats = {"rss": 0, "blocked": 0, "approved": 0, "selected": 0, "downloaded": 0, "paragraphs": 0}

    _ensure_connectivity()

    store = SeenStore(SEEN_DB)
    store.prune(SEEN_RETENTION_DAYS)

    print("Leyendo feeds RSS...")
    items = fetch_items()
    stats["rss"] = len(items)
    print(f"  {len(items)} items obtenidos")

    store.note_seen(items, date.today().isoformat())
    blocked = [it for it in items if store.is_blocked(it.url, it.title, it.source)]
    stats["blocked"] = len(blocked)
    if blocked:
        print(f"  {len(blocked)} items ya enviados en un digest anterior — descartados")
        for it in blocked:
            print(f"    → {it.title[:80]}")
    items = [it for it in items if it not in blocked]

    print("Filtrando por relevancia...")
    approved = filter_items(items)
    stats["approved"] = len(approved)
    print(f"  {len(approved)} items aprobados")

    if not approved:
        print("ERROR: Ningún item superó el filtro de relevancia")
        _write_run_log("FALLO — Ningún item superó el filtro de relevancia", stats)
        sys.exit(1)

    print("Deduplicando por evento...")
    approved = deduplicate_by_event(approved)
    print(f"  {len(approved)} items tras dedup")

    print(f"Seleccionando por puntaje y cuotas...")
    selected = select_by_quota(approved)
    stats["selected"] = len(selected)
    print(f"  {len(selected)} items seleccionados:")
    for it in selected:
        print(f"    [{it.score}] {it.section[:30]:30s} {it.title[:80]}")

    print("Descargando artículos completos...")
    article_texts = fetch_all_articles(selected)
    stats["downloaded"] = len(article_texts)
    print(f"  {len(article_texts)}/{len(selected)} artículos descargados")

    print("Generando párrafos...")
    paragraphs: list = []
    total = len(selected)
    for i, item in enumerate(selected, 1):
        print(f"  [{i}/{total}] {item.source} — {item.title[:70]}")
        full_text = article_texts.get(item.url)
        if not full_text:
            print(f"    → no se pudo descargar el artículo")
            continue

        paragraph = generate_paragraph(item, full_text)
        if not paragraph:
            print(f"    → no se pudo generar párrafo")
            continue

        stats["paragraphs"] += 1
        item.paragraph_md = paragraph
        paragraphs.append(item)

    if len(paragraphs) < MIN_ITEMS_FOR_DIGEST:
        reason = "No se generaron noticias" if not paragraphs else f"Solo se generaron {len(paragraphs)} noticias (mínimo {MIN_ITEMS_FOR_DIGEST})"
        print(f"ERROR: {reason}")
        _write_run_log(f"FALLO — {reason}", stats)
        sys.exit(1)

    news_text = assemble(paragraphs)

    (PROJECT_ROOT / "debug_news.txt").write_text(news_text, encoding="utf-8")

    print("Revisión editorial (por sección)...")
    editorial_blocked = False
    gate_failed_sections = []
    rejected_sections = []
    sections = [s for s in re.split(r'\n(?=## )', news_text) if s.strip()]
    for i, section in enumerate(sections):
        section_header = section.split("\n", 1)[0].strip()
        print(f"  Revisando {section_header}...")
        result = review(section)
        if result is None:
            print(f"    APROBADO")
        elif is_rejection(result):
            rejected_sections.append(section_header)
            print(f"    ⚠ RECHAZADO (no bloqueante) — {result[:200]}")
        elif is_gate_failure(result):
            gate_failed_sections.append(section_header)
            print(f"    ⚠ editor no respondió")
        else:
            print(f"    Correcciones: {result[:200]}")
        if i < len(sections) - 1:
            time.sleep(5)

    if rejected_sections:
        print(f"  ⚠ Editor rechazó: {', '.join(rejected_sections)} — pero el digest se envía de todos modos")

    if gate_failed_sections:
        print(f"  ⚠ Editor no respondió para: {', '.join(gate_failed_sections)} — se envía SIN revisar esas secciones")

    html_path = PROJECT_ROOT / HTML_FILENAME
    print("Construyendo HTML...")
    html_content = build_html(news_text, html_path)

    mp3_path = PROJECT_ROOT / MP3_FILENAME
    tts_text = strip_markdown(news_text)
    print("Sintetizando audio...")
    audio_bytes = asyncio.run(synthesize(tts_text, mp3_path))

    print("Enviando correo electrónico...")
    send(html_content, audio_bytes, DATE_STAMP)

    store.mark_sent(paragraphs, date.today().isoformat())

    print("Limpiando archivos temporales...")
    mp3_path.unlink(missing_ok=True)
    html_path.unlink(missing_ok=True)

    status = f"OK — correo enviado a {EMAIL_TO}"
    notes = []
    if rejected_sections:
        notes.append(f"editor rechazó: {', '.join(rejected_sections)}")
    if gate_failed_sections:
        notes.append(f"sin revisión: {', '.join(gate_failed_sections)}")
    if notes:
        status += f" ({'; '.join(notes)})"
    _write_run_log(status, stats)
    store.close()
    print("¡Listo! Digest 13 entregado.")


if __name__ == "__main__":
    main()
