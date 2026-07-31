import re
from llm import call_llm
from web_searcher import Item

SYSTEM_PROMPT = "Eres un editor de noticias. Evalúa cada item con puntaje del 1 al 5."

USER_PROMPT = """Evalúa este artículo para el boletín informativo "Digest 13".

## Secciones del boletín
• GEOPOLÍTICA Y AMÉRICA LATINA: conflictos armados, macroeconomía, relaciones bilaterales, crisis de gobernanza, control de recursos, comercio internacional, política exterior.
• POLÍTICA Y SOCIEDAD COSTARRICENSE: fiscalización del poder público, proyectos de ley, resoluciones judiciales, deuda, inflación, infraestructura, seguridad, salud pública, educación.
• TECNOLOGÍA, INFRAESTRUCTURA Y SOFTWARE: IA, ciberseguridad, hardware, software, soberanía digital, regulación tecnológica, startups.

## Criterios de RECHAZO (PUNTAJE = 1)
- Deportes, fútbol, Mundiales, competencias atléticas
- Efemérides, aniversarios, conmemoraciones, actos protocolarios
- Noticias universitarias (logros estudiantiles, SINDEU, fedes, boletines)
- Comunicados de prensa corporativos o contenido promocional
- Pifias diplomáticas, mapas errados, declaraciones sin efecto
- Lanzamientos de gadgets de consumo, videojuegos a precio completo
- Pseudociencia, medicina alternativa, homeopatía, curación energética, terapias no comprobadas
- Contenido antivacunas, teorías conspirativas sobre salud
- Reportajes sobre doulas, parteras o partos no asistidos como alternativa a la atención médica profesional

## Escala de puntaje
5 = IMPERDIBLE: impacto global directo, crisis mayor, cambio de políticas, revelación importante
4 = ALTA RELEVANCIA: afecta significativamente a la región o sector
3 = RELEVANCIA MEDIA: informativo, contexto útil, tendencia notable
2 = BAJA RELEVANCIA: tangencial, muy localizado, rumor, especulación
1 = RECHAZAR: aplica algún criterio de rechazo

Título: {title}
Fuente: {source}
Extracto: {summary}

Responde estrictamente este formato:

PUNTAJE: [1-5]
ACCIÓN: [APROBAR|RECHAZAR]
SECCIÓN: [GEOPOLÍTICA Y AMÉRICA LATINA|POLÍTICA Y SOCIEDAD COSTARRICENSE|TECNOLOGÍA, INFRAESTRUCTURA Y SOFTWARE]
MOTIVO: [razón breve]"""


def _parse_score(answer: str) -> int:
    m = re.search(r"PUNTAJE\s*:\s*(\d+)", answer, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def _parse_action(answer: str) -> str:
    m = re.search(r"ACCIÓN\s*:\s*(APROBAR|RECHAZAR)", answer, re.IGNORECASE)
    return m.group(1).upper() if m else "RECHAZAR"


def _parse_section(answer: str) -> str | None:
    m = re.search(
        r"SECCIÓN\s*:\s*(GEOPOLÍTICA Y AMÉRICA LATINA|POLÍTICA Y SOCIEDAD COSTARRICENSE|TECNOLOGÍA, INFRAESTRUCTURA Y SOFTWARE)",
        answer,
        re.IGNORECASE,
    )
    return m.group(1) if m else None


def filter_items(items: list[Item]) -> list[Item]:
    approved: list[Item] = []

    for item in items:
        user = USER_PROMPT.format(
            title=item.title,
            source=item.source,
            summary=item.summary[:500],
        )
        answer = call_llm(SYSTEM_PROMPT, user, max_tokens=300)
        if not answer:
            print(f"  ERROR: sin respuesta para {item.title[:60]}")
            continue

        score = _parse_score(answer)
        action = _parse_action(answer)

        if action == "RECHAZAR" or score < 2:
            reason_match = re.search(r"MOTIVO\s*:\s*(.+)", answer, re.IGNORECASE | re.DOTALL)
            reason = reason_match.group(1).strip() if reason_match else "sin motivo"
            if score > 0:
                print(f"  RECHAZADO (score={score}): {item.title[:60]} — {reason}")
            else:
                print(f"  RECHAZADO: {item.title[:60]} — {reason}")
            continue

        section = _parse_section(answer)
        if section:
            item.section = section
        item.score = score
        approved.append(item)
        # Print only first 60 chars of reason to keep it readable
        reason_match = re.search(r"MOTIVO\s*:\s*(.+)", answer, re.IGNORECASE | re.DOTALL)
        reason = reason_match.group(1).strip()[:60] if reason_match else ""
        print(f"  APROBADO (score={score}): {item.title[:60]} — {reason}")

    return approved
