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


def _parse_score(answer: str) -> int | None:
    m = re.search(r"PUNTAJE\s*:\s*(\d+)", answer, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _parse_action(answer: str) -> str | None:
    m = re.search(r"ACCIÓN\s*:\s*(APROBAR|RECHAZAR)", answer, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _parse_section(answer: str) -> str | None:
    m = re.search(
        r"SECCIÓN\s*:\s*(GEOPOLÍTICA Y AMÉRICA LATINA|POLÍTICA Y SOCIEDAD COSTARRICENSE|TECNOLOGÍA, INFRAESTRUCTURA Y SOFTWARE)",
        answer,
        re.IGNORECASE,
    )
    return m.group(1) if m else None


def filter_items(items: list[Item]) -> list[Item]:
    approved: list[Item] = []
    malformed = 0

    for item in items:
        user = USER_PROMPT.format(
            title=item.title,
            source=item.source,
            summary=item.summary[:500],
        )
        answer = call_llm(SYSTEM_PROMPT, user, max_tokens=600)
        if not answer:
            print(f"  ERROR: sin respuesta para {item.title[:60]}")
            continue

        action = _parse_action(answer)
        score = _parse_score(answer)

        # Distinguish "the model evaluated and rejected it" from "the model
        # didn't follow the PUNTAJE:/ACCIÓN: format at all" — the latter must
        # never be silently treated as a rejection, or a model that ignores
        # the format (e.g. an unfamiliar fallback) tanks the whole run
        # looking exactly like a legitimate low-relevance day.
        if action is None or score is None:
            malformed += 1
            print(f"  MALFORMADO (no se pudo parsear PUNTAJE/ACCIÓN): {item.title[:60]} — respuesta: {answer[:100]!r}")
            continue

        if action == "RECHAZAR" or score < 2:
            reason_match = re.search(r"MOTIVO\s*:\s*(.+)", answer, re.IGNORECASE | re.DOTALL)
            reason = reason_match.group(1).strip() if reason_match else "sin motivo"
            print(f"  RECHAZADO (score={score}): {item.title[:60]} — {reason}")
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

    if malformed:
        ratio = malformed / len(items) if items else 0
        print(f"  ⚠ {malformed}/{len(items)} respuestas malformadas ({ratio:.0%}) — el modelo puede no estar siguiendo el formato PUNTAJE:/ACCIÓN:")

    return approved


DEDUP_SYSTEM_PROMPT = "Eres un editor de noticias que agrupa reportajes del mismo evento."

DEDUP_USER_PROMPT = """Estos son los titulares aprobados para el boletín (ID, sección, fuente, título):

{items}

Agrupa únicamente los items que cubren el MISMO evento o la MISMA noticia de fondo (misma crisis, mismo incidente, mismo tema específico). No agrupes temas simplemente relacionados o de la misma región: "dos reportajes distintos sobre la misma guerra" NO son duplicados; "dos reportajes sobre el MISMO ataque/incidente/crisis puntual" sí.

Por cada grupo de duplicados responde una línea:

GRUPO: [IDs separados por coma]

Si no hay duplicados responde solo: SIN DUPLICADOS"""


def _parse_groups(answer: str) -> list[list[int]]:
    groups: list[list[int]] = []
    for m in re.finditer(r"GRUPO\s*:\s*([\d,\s]+)", answer, re.IGNORECASE):
        ids = [int(x) for x in re.findall(r"\d+", m.group(1))]
        if len(ids) >= 2:
            groups.append(ids)
    return groups


def deduplicate_by_event(items: list[Item]) -> list[Item]:
    if len(items) < 4:
        return items

    # Only the top candidates by score can make the digest; dedup where it matters
    pool = sorted(items, key=lambda i: (-i.score, i.title))[:20]
    lines = []
    for i, item in enumerate(pool, 1):
        title = item.title.replace("\n", " ")[:120]
        summary = re.sub(r"\s+", " ", item.summary[:150]).strip()
        lines.append(f"{i}. [{item.section[:20]}] {item.source} | {title} — {summary}")

    answer = call_llm(DEDUP_SYSTEM_PROMPT, DEDUP_USER_PROMPT.format(items="\n".join(lines)), max_tokens=600)
    if not answer:
        print("  (dedup: sin respuesta, se omite)")
        return items

    groups = _parse_groups(answer)
    if not groups:
        print("  (dedup: SIN DUPLICADOS)")
        return items

    drop: set[int] = set()
    for group in groups:
        group = [g for g in group if 1 <= g <= len(pool)]
        if len(group) < 2:
            continue
        best = max(group, key=lambda g: pool[g - 1].score)
        for g in group:
            if g != best:
                drop.add(g)

    if not drop:
        print("  (dedup: SIN DUPLICADOS)")
        return items

    dropped = [pool[idx - 1] for idx in drop]
    kept = [item for item in items if item not in dropped]
    print(f"  dedup: {len(drop)} duplicado(s) descartado(s):")
    for idx in sorted(drop):
        print(f"    → {pool[idx - 1].source} — {pool[idx - 1].title[:70]}")
    return kept
