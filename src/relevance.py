from llm import call_llm
from web_searcher import Item

SYSTEM_PROMPT = "Eres un editor de noticias. Decide rápido si un item es apto o no para el boletín."

USER_PROMPT = """El boletín tiene TRES secciones, cada una con su propio criterio:
• GEOPOLÍTICA: conflictos armados, macroeconomía, relaciones bilaterales, crisis de gobernanza, control de recursos, comercio internacional.
• POLÍTICA COSTARRICENSE: fiscalización del poder público, proyectos de ley, resoluciones judiciales, deuda, inflación, infraestructura, seguridad.
• TECNOLOGÍA: IA, ciberseguridad, hardware, software, soberanía digital, regulación tecnológica.

Título: {title}
Fuente: {source}
Extracto: {summary}

RECHAZAR si aplica ALGUNA:
- Deportes, fútbol, Mundiales, competencias atléticas
- Efemérides, aniversarios, conmemoraciones, actos protocolarios
- Noticias universitarias (logros estudiantiles, SINDEU, fedes, boletines)
- Comunicados de prensa corporativos o contenido promocional
- Pifias diplomáticas, mapas errados, declaraciones sin efecto
- Lanzamientos de gadgets de consumo, videojuegos a precio completo

Responde solo APROBAR o RECHAZAR. Si RECHAZAS, di el motivo."""


def filter_items(items: list[Item]) -> list[Item]:
    approved: list[Item] = []

    for item in items:
        user = USER_PROMPT.format(
            title=item.title,
            source=item.source,
            summary=item.summary[:500],
        )
        answer = call_llm(SYSTEM_PROMPT, user, max_tokens=50)
        if not answer:
            print(f"  ERROR: sin respuesta para {item.title[:60]}")
            continue
        if answer.upper().startswith("APROBAR"):
            approved.append(item)
        else:
            reason = answer.replace("RECHAZAR", "").strip().lstrip(":").strip()
            print(f"  RECHAZADO: {item.title[:60]} — {reason}")

    return approved
