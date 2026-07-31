import asyncio
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from config import PROJECT_ROOT
from web_searcher import fetch_items
from relevance import filter_items, deduplicate_by_event
from article_fetcher import fetch_full_text
from paragraph_gen import generate_paragraph
from editorial_review import review
from html_generator import build_html
from text_cleaner import strip_markdown
from tts_engine import synthesize
from email_sender import send

DATE_STAMP = date.today().strftime("%Y.%m.%d")
MP3_FILENAME = f"digest13.{DATE_STAMP}.mp3"
HTML_FILENAME = f"digest13.{DATE_STAMP}.html"

SECTION_ORDER = [
    "GEOPOLÍTICA Y AMÉRICA LATINA",
    "POLÍTICA Y SOCIEDAD COSTARRICENSE",
    "TECNOLOGÍA, INFRAESTRUCTURA Y SOFTWARE",
]

SECTION_QUOTAS: dict[str, dict] = {
    "GEOPOLÍTICA Y AMÉRICA LATINA": {"max": 6},
    "POLÍTICA Y SOCIEDAD COSTARRICENSE": {"min": 3, "max": 5},
    "TECNOLOGÍA, INFRAESTRUCTURA Y SOFTWARE": {"max": 5},
}
MAX_TOTAL = 15
TOKEN_LIMIT = 60_000


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
    cr_key = "POLÍTICA Y SOCIEDAD COSTARRICENSE"
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
    print("Leyendo feeds RSS...")
    items = fetch_items()
    print(f"  {len(items)} items obtenidos")

    print("Filtrando por relevancia...")
    approved = filter_items(items)
    print(f"  {len(approved)} items aprobados")

    if not approved:
        print("ERROR: Ningún item superó el filtro de relevancia")
        return

    print("Deduplicando por evento...")
    approved = deduplicate_by_event(approved)
    print(f"  {len(approved)} items tras dedup")

    print(f"Seleccionando por puntaje y cuotas...")
    selected = select_by_quota(approved)
    print(f"  {len(selected)} items seleccionados:")
    for it in selected:
        print(f"    [{it.score}] {it.section[:30]:30s} {it.title[:80]}")

    approx_tokens = 0

    print("Descargando artículos completos y generando párrafos...")
    paragraphs: list = []
    total = len(selected)
    for i, item in enumerate(selected, 1):
        if approx_tokens >= TOKEN_LIMIT:
            print(f"  [budget agotado] procesados {i-1}/{total}, restantes saltados")
            break

        print(f"  [{i}/{total}] {item.source} — {item.title[:70]}")
        full_text = fetch_full_text(item.url)
        if not full_text:
            print(f"    → no se pudo descargar el artículo")
            continue

        paragraph = generate_paragraph(item, full_text)
        if not paragraph:
            print(f"    → no se pudo generar párrafo")
            continue

        approx_tokens += (len(full_text[:2500]) + len(paragraph)) // 4
        item.paragraph_md = paragraph
        paragraphs.append(item)

    if not paragraphs:
        print("ERROR: No se generaron noticias")
        return

    news_text = assemble(paragraphs)

    (PROJECT_ROOT / "debug_news.txt").write_text(news_text, encoding="utf-8")

    print("Revisión editorial...")
    approx_tokens += len(news_text) // 4
    if approx_tokens < TOKEN_LIMIT:
        review_result = review(news_text)
        if review_result:
            print(f"  Pendiente de corrección: {review_result[:200]}")
        else:
            print("  APROBADO")
    else:
        print("  (saltada por presupuesto de tokens)")

    html_path = PROJECT_ROOT / HTML_FILENAME
    print("Construyendo HTML...")
    html_content = build_html(news_text, html_path)

    mp3_path = PROJECT_ROOT / MP3_FILENAME
    tts_text = strip_markdown(news_text)
    print("Sintetizando audio...")
    audio_bytes = asyncio.run(synthesize(tts_text, mp3_path))

    print("Enviando correo electrónico...")
    send(html_content, audio_bytes, DATE_STAMP)

    print("Limpiando archivos temporales...")
    mp3_path.unlink(missing_ok=True)
    html_path.unlink(missing_ok=True)

    print("¡Listo! Digest 13 entregado.")


if __name__ == "__main__":
    main()
