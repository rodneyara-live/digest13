import re
from llm import call_llm
from web_searcher import Item

SYSTEM_PROMPT = "Eres un analista de prensa que escribe párrafos densos en datos para un boletín. Responde SIEMPRE en español."

USER_PROMPT = """Artículo:
{full_text}

Escribe:
### [Título descriptivo y directo]
[Párrafo de 3 a 5 oraciones: HECHO con cifras/nombres/fechas, CONTEXTO, IMPLICACIÓN.]

Prohibido: "es importante", "genera debate", "situación delicada", "es un logro/paso". Solo datos.
Responde SOLO en español. No incluyas razonamiento ni texto explicativo — solo el título y el párrafo."""


def generate_paragraph(item: Item, full_text: str) -> str | None:
    truncated = full_text[:2500]
    user = USER_PROMPT.format(full_text=truncated)
    text = call_llm(SYSTEM_PROMPT, user, max_tokens=2500, temperature=0.4)
    if not text:
        return None
    text = re.sub(r"^###\s*\[?(.+?)\]?\s*$", f"### [\\1]({item.url})", text, count=1, flags=re.MULTILINE)
    return text
