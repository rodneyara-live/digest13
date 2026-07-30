from llm import call_llm
from web_searcher import Item

SYSTEM_PROMPT = "Eres un analista de prensa que escribe párrafos densos en datos para un boletín."

USER_PROMPT = """Artículo:
{full_text}

Escribe:
### [Título descriptivo y directo]
[Párrafo de 3 a 5 oraciones: HECHO con cifras/nombres/fechas, CONTEXTO, IMPLICACIÓN.]
*(Fuente: {source})*

Prohibido: "es importante", "genera debate", "situación delicada", "es un logro/paso". Solo datos."""


def generate_paragraph(item: Item, full_text: str) -> str | None:
    truncated = full_text[:2500]
    user = USER_PROMPT.format(full_text=truncated, source=item.source)
    text = call_llm(SYSTEM_PROMPT, user, max_tokens=400, temperature=0.4)
    if text:
        return text
    return None
