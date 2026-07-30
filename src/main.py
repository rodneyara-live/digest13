import asyncio
from datetime import date
from pathlib import Path
from config import PROJECT_ROOT
from web_searcher import fetch_items
from relevance import filter_items
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

TOKEN_LIMIT = 90_000
_approx_tokens = 0


def _section_rank(section: str) -> int:
    try:
        return SECTION_ORDER.index(section)
    except ValueError:
        return 99


def assemble(items: list[tuple[str, str]]) -> str:
    sections: dict[str, list[str]] = {}
    for section, md in items:
        sections.setdefault(section, []).append(md)

    parts = []
    for section in SECTION_ORDER:
        paras = sections.get(section)
        if paras:
            parts.append(f"## {section}")
            parts.extend(paras)
            parts.append("")
    return "\n".join(parts).strip()


def main() -> None:
    global _approx_tokens

    print("Leyendo feeds RSS...")
    items = fetch_items()
    print(f"  {len(items)} items obtenidos")

    print("Filtrando por relevancia...")
    approved = filter_items(items)
    print(f"  {len(approved)} items aprobados")

    if not approved:
        print("ERROR: Ningún item superó el filtro de relevancia")
        return

    approved.sort(key=lambda i: (_section_rank(i.section), i.title))

    print("Descargando artículos completos y generando párrafos...")
    paragraphs: list[tuple[str, str]] = []
    total = len(approved)
    for i, item in enumerate(approved, 1):
        if _approx_tokens >= TOKEN_LIMIT:
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

        # rough token estimate: 1 token ≈ 4 chars (Spanish)
        _approx_tokens += (len(full_text[:2500]) + len(paragraph)) // 4
        paragraphs.append((item.section, paragraph))

    news_text = assemble(paragraphs)
    if not news_text:
        print("ERROR: No se generaron noticias")
        return

    (PROJECT_ROOT / "debug_news.txt").write_text(news_text, encoding="utf-8")

    print("Revisión editorial...")
    _approx_tokens += len(news_text) // 4
    if _approx_tokens < TOKEN_LIMIT:
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
