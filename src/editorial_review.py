from llm import call_llm
from config import EDITORIAL_MODEL

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


def review(news_text: str) -> str | None:
    if not news_text.strip():
        return "INFORME VACÍO"

    answer = call_llm(
        SYSTEM_PROMPT,
        USER_PROMPT.format(news_text=news_text[:8000]),
        max_tokens=1500,
        temperature=0.2,
        model=EDITORIAL_MODEL,
    )
    if not answer:
        return "ERROR: sin respuesta de revisión"
    if answer.upper().startswith("APROBADO"):
        return None
    return answer
