from llm import call_llm
from config import EDITORIAL_MODEL

SYSTEM_PROMPT = "Eres un editor en jefe que revisa calidad y consistencia editorial."

USER_PROMPT = """Revisa este informe:

{news_text}

Verifica cada noticia:
1. ¿Tiene estructura ### [Título] + párrafo + *(Fuente: ...)*?
2. ¿Evita frases vagas como "es importante", "genera debate", "situación delicada", "es un logro/paso importante"?
3. ¿Usa datos concretos (cifras, nombres, fechas)?
4. ¿Hay dos noticias que cubren el MISMO evento o la misma noticia de fondo? Si sí, indica el título exacto de la que conservar y de la que descartar.

Responde solo APROBADO o una lista de correcciones específicas."""


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
