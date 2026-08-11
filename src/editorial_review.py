import re
from llm import call_llm
from config import EDITORIAL_MODEL

# A full 15-item digest runs ~12.5K chars. The cap exists only to bound a runaway
# run, so it sits well above that: an 8000-char cap left the editor blind to the
# last third of the report — the entire TECNOLOGÍA section — while still being
# billed as a full review.
MAX_REVIEW_CHARS = 12000

SYSTEM_PROMPT = """Eres el editor en jefe y ÚLTIMA línea de defensa de calidad del boletín "Digest 13".
Tu trabajo es RECHAZAR o CORREGIR — no aprobar ciegamente.

Criterios de RECHAZO (si cualquiera aplica, RECHAZA el digest completo):
- Párrafos con formato roto: JSON, XML, thinking/reasoning visible, listas con viñetas, o cualquier cosa que no sea ### [Título](url) + párrafo en prosa
- Párrafos vacíos o que solo contienen el título sin contenido
- Contenido de farándula, espectáculos, chismes, o basura que no encaja en geopolítica/CR/tech
- Datos inventados o contradictorios entre noticias del mismo evento
- Más de 2 noticias cubriendo el MISMO evento de fondo (indica cuáles consolidar)

Criterios de CORRECCIÓN (lista los problemas encontrados):
- Estructura incorrecta (falta ###, falta url, falta párrafo)
- Frases vagas prohibidas: "es importante", "genera debate", "situación delicada", "es un logro/paso"
- Párrafo demasiado largo o demasiado corto (menos de 3 oraciones)
- Noticias repetidas o muy similares que deben fusionarse

Formato de respuesta:
- Si el digest es APTO para publicación: responde SOLO "APROBADO"
- Si hay problemas: responde una lista numerada de problemas y qué hacer con cada uno
- Si el digest es RECHAZABLE: responde "RECHAZADO: [razón]" y lista las noticias que deben eliminarse"""


USER_PROMPT = """Revisa este informe completo:

{news_text}

Lee CADA noticia. Verifica la estructura, el contenido y la calidad general.
Responde APROBADO, una lista de correcciones, o RECHAZADO."""


def _verdict(answer: str) -> str:
    """The model leads with its verdict but decorates it — `**RECHAZADO:**`, `### APROBADO`,
    a leading blank line. Strip that before matching: a plain `startswith` misses
    `**RECHAZADO:**` entirely, which makes the gate fail *open* and mail a digest the
    editor rejected."""
    return re.sub(r"^[\s*_#>`\-]+", "", answer).upper()


GATE_ERROR = "ERROR: sin respuesta de revisión"


def is_rejection(review_result: str) -> bool:
    """True when the editor rejected the whole digest (vs. listing corrections)."""
    return _verdict(review_result).startswith("RECHAZADO")


def is_gate_failure(review_result: str) -> bool:
    """True when the gate itself couldn't run — no response, or one truncated by
    `max_tokens` before the verdict came out. That is not an approval: the digest
    ships unreviewed, so the run log has to say so instead of reporting a clean OK."""
    return review_result.startswith(GATE_ERROR)


def _fit(news_text: str) -> str:
    """Trim to whole news items, never mid-line. A sliced URL reads to the editor as
    a broken link and the straddled item as a title with no paragraph, so a raw
    character cut makes it report defects that aren't in the digest at all (observed
    in the 2026-08-01 12:48 run, which flagged a perfectly good Semanario item)."""
    if len(news_text) <= MAX_REVIEW_CHARS:
        return news_text
    cut = news_text.rfind("\n### ", 0, MAX_REVIEW_CHARS)
    if cut <= 0:
        cut = news_text.rfind("\n", 0, MAX_REVIEW_CHARS)
    fitted = news_text[:cut].rstrip() if cut > 0 else news_text[:MAX_REVIEW_CHARS]
    print(f"  ⚠ informe de {len(news_text)} chars recortado a {len(fitted)} para la revisión")
    return fitted


def review(news_text: str) -> str | None:
    if not news_text.strip():
        return "INFORME VACÍO"

    answer = call_llm(
        SYSTEM_PROMPT,
        USER_PROMPT.format(news_text=_fit(news_text)),
        max_tokens=1500,
        temperature=0.2,
        model=EDITORIAL_MODEL,
    )
    if not answer:
        return GATE_ERROR
    if _verdict(answer).startswith("APROBADO"):
        return None
    return answer
