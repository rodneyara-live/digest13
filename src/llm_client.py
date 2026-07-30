from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL

PROMPT = """Actúa como un editor y analista de prensa internacional. Tu tarea es elaborar un informe diario de noticias con un enfoque técnico, analítico, riguroso y sin sensacionalismo.

REGLAS STRICTAS DE FORMATO Y ESTRUCTURA:
- Cada sección DEBE contener notas periodísticas 100% INDEPENDIENTES entre sí.
- Queda ESTRICTAMENTE PROHIBIDO redactar ensayos continuos, fusionar noticias dentro de un mismo párrafo o usar conectores como "Por otro lado", "En paralelo" o "En materia de...".
- Cada noticia DENTRO de una sección DEBE llevar obligatoriamente esta estructura:
  ### [Título descriptivo y directo de la noticia]
  [Un único párrafo explicativo de 3 a 5 oraciones que detalle: el HECHO, el CONTEXTO y la IMPLICACIÓN técnica o política.]
  *(Fuente: [Nombre del medio])*

CONTENIDO Y COBERTURA POR SECCIÓN:

1. GEOPOLÍTICA Y AMÉRICA LATINA (Fuentes de referencia tipo The Guardian)
   - Selecciona hasta 6 acontecimientos globales de alto impacto.
   - Proporción obligatoria: Incluye al menos 2 temas relevantes de América Latina o el Sur Global para evitar un sesgo puramente eurocéntrico.

2. POLÍTICA Y SOCIEDAD COSTARRICENSE (Fuentes: Delfino.cr, Semanario Universidad)
   - Selecciona hasta 6 temas sobre la realidad institucional, económica y social de Costa Rica.
   - Incluye al menos 1 o 2 noticias de Semanario Universidad por tirada.
   - Prioriza la fiscalización del poder público, decisiones judiciales/legislativas y variables macroeconómicas/fiscales.
   - EXCLUSIÓN ABSOLUTA: Farándula, deportes, sucesos amarillistas y comunicados de prensa corporativos.

3. TECNOLOGÍA, FOTOGRAFÍA Y CULTURA DIGITAL
   - Selecciona entre 2 y 4 temas de fondo.
   - Enfoque: Infraestructura de IA, ciberseguridad, soberanía de software, privacidad, o debates sobre fotografía técnica y óptica dedicada frente al procesamiento sintético.
   - EXCLUSIÓN ABSOLUTA: Lanzamientos de teléfonos, "gadgets" menores o contenido promocional.

Tono: Imparcial, directo, técnico y de nivel profesional."""


def generate_news(context: str | None = None) -> str:
    if context:
        full_prompt = (
            "Resultados de búsqueda web de hoy:\n\n"
            f"{context}\n\n"
            "---\n\n"
            "Con base ÚNICAMENTE en los resultados de búsqueda anteriores, "
            "elabora un informe diario de noticias. Sigue estas reglas:\n\n"
            + PROMPT
        )
    else:
        full_prompt = PROMPT

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": full_prompt}],
    )
    return response.choices[0].message.content
