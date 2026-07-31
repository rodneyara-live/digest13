from llm import call_llm

SYSTEM_PROMPT = "Eres un editor en jefe que revisa calidad y consistencia editorial."

USER_PROMPT = """Revisa este informe:

{news_text}

Verifica cada noticia:
1. ¿Tiene estructura ### [Título] + párrafo + *(Fuente: ...)*?
2. ¿Evita frases vagas como "es importante", "genera debate", "situación delicada", "es un logro/paso importante"?
3. ¿Usa datos concretos (cifras, nombres, fechas)?

Responde solo APROBADO o una lista de correcciones específicas."""


def review(news_text: str) -> str | None:
    if not news_text.strip():
        return "INFORME VACÍO"

    answer = call_llm(SYSTEM_PROMPT, USER_PROMPT.format(news_text=news_text[:8000]), max_tokens=1500, temperature=0.2)
    if not answer:
        return "ERROR: sin respuesta de revisión"
    if answer.upper().startswith("APROBADO"):
        return None
    return answer
