# Digest 13 — Backlog de ideas (post-iteración)

Recomendaciones para aplicar **cuando el pipeline y el contenido resultante ya estén a gusto** y se
quiera pasar de "modo experimentación" a "servicio desatendido estable". Ordenadas por prioridad —
la lista está pensada para retomarse tanto acá como con cualquier otro agente (p. ej. Big Pickle).

**Contexto de prioridad, importante para no sobre-optimizar lo que no importa:** este es un proyecto
personal de un solo usuario, corriendo sobre la cuota gratuita de Groq (200K tokens/día). El costo de
tokens **no es una preocupación** — lo que importa es la calidad del resultado final (curación, edición,
redacción) y no perder interacciones por límites artificialmente estrechos. Cualquier recomendación que
suene a "ahorrar tokens" debe pesarse contra esto: aquí se prefiere gastar de más a perder una llamada.

## Prioridad 1 (siguiente a atender) — `max_tokens` demasiado ajustados, riesgo de rechazo silencioso

Como `openai/gpt-oss-120b` es un modelo *reasoning*, gasta tokens en cadena de pensamiento oculta
**antes** de escribir la respuesta visible, y ambas cosas comparten el mismo presupuesto de `max_tokens`
de la llamada. Si el modelo se queda sin espacio pensando, la respuesta llega truncada o vacía — no como
error, sino como texto incompleto.

El caso más delicado es [relevance.py](src/relevance.py) con `max_tokens=300` — la etapa que corre una
vez por cada ítem de RSS crudo (30-50 llamadas por corrida). Si la respuesta se corta antes de la línea
`ACCIÓN:`, `_parse_action()` en [relevance.py:49-51](src/relevance.py:49) cae al default:
```python
return m.group(1).upper() if m else "RECHAZAR"
```
Es decir: un ítem que el modelo sí iba a aprobar puede desaparecer del digest **silenciosamente**, no
porque el modelo lo rechazó, sino porque el límite de tokens lo cortó a medio pensamiento. No hay señal
visible de que esto esté pasando — el log solo dice "RECHAZADO" con el motivo que haya alcanzado a
parsear (o "sin motivo" si ni eso).

Importante: subir `max_tokens` **no necesariamente cuesta más cuota**. Solo se paga por lo que el modelo
realmente genera, no por el techo. Si hoy se está truncando, esos tokens de razonamiento ya se están
gastando sin producir nada útil — la llamada se pierde sin reintento. Subir el límite puede incluso
ahorrar, al evitar llamadas fallidas que haya que re-ejecutar.

**Acción:**
- Subir `relevance.py` de 300 → 600-800 tokens (es la más ajustada relativa a lo que "debería" necesitar
  para un formato de 4 líneas).
- Revisar también `paragraph_gen.py` (600) y `editorial_review.py` (1500) con el mismo criterio: mejor
  sobrado que corto.
- En vez de adivinar, instrumentar `llm.py` para loguear `response.choices[0].finish_reason` en cada
  llamada ([llm.py:28](src/llm.py:28)) — si el valor es `"length"`, es la prueba directa de truncamiento,
  en vez de estimarlo a ojo. Con eso se puede calibrar los límites con datos reales de uso, no con
  suposiciones.

## Prioridad 2 — Corrección: descompresión gzip/brotli en `article_fetcher.py`

`_decompress()` ([article_fetcher.py:16](src/article_fetcher.py:16)) soporta gzip/zlib/brotli pero
**nunca se invoca**. `fetch_full_text()` solo aplica el chequeo manual de gzip (`\x1f\x8b`) en las
líneas 36-38; el resto de la función queda muerta. Esto es justo lo que rompe la extracción de
Semanario Universidad cuando el servidor responde con una variante de compresión que `requests` no
auto-decodifica.

**Acción:** conectar `_decompress()` como fallback real, por ejemplo:
```python
content = resp.content
if content[:2] == b"\x1f\x8b" or resp.headers.get("Content-Encoding") in ("gzip", "br", "deflate"):
    content = _decompress(content)
html = content.decode("utf-8", errors="replace")
text = trafilatura.extract(html)
if not text or len(text.strip()) <= 100:
    # reintentar decodificando con _decompress si no se hizo arriba
    ...
```
Probar específicamente contra la URL del feed de Semanario Universidad hasta confirmar que
`trafilatura.extract()` deja de fallar ahí.

## Prioridad 3 — Feature: hipervínculo al artículo original en el título H3, quitar atribución textual

Hoy cada noticia cierra con `*(Fuente: {source})*` como texto plano (definido en el prompt de
[paragraph_gen.py:11-12](src/paragraph_gen.py:11)). La idea: en vez de esa línea de atribución al final,
convertir el título `### [Título]` en un hipervínculo directo al artículo original, para poder hacer clic
y leer la nota completa en el medio de origen cuando un tema interese ampliar.

El dato ya existe sin necesidad de extraer nada nuevo — `Item.url` ([web_searcher.py:10](src/web_searcher.py:10))
se captura desde el RSS original y llega intacto hasta `generate_paragraph(item, full_text)` en
[paragraph_gen.py:17](src/paragraph_gen.py:17).

**Punto de diseño importante:** no conviene pedirle al LLM que escriba la URL él mismo dentro del texto
generado — los modelos tienden a truncar, reformatear o inventar URLs largas. El enfoque correcto es:
1. Dejar que el LLM siga generando solo el texto del título en la línea `###` (como ya hace).
2. En Python, extraer ese texto de título de la respuesta (regex sobre la primera línea `### ...`) y
   reconstruir la línea como `### [{título}]({item.url})`, inyectando la URL real del `Item`, no la que
   "recuerde" el modelo.
3. Quitar del prompt la instrucción de cerrar con `*(Fuente: {source})*`.

`html_generator.py` no necesita cambios: `markdown.markdown(news_text, extensions=["extra"])` ya convierte
`[texto](url)` dentro de un `###` en `<h3><a href="...">texto</a></h3>` sin configuración adicional. Si se
quiere que el enlace abra en pestaña nueva (`target="_blank"`), sí habría que post-procesar el HTML
generado, ya que python-markdown no agrega ese atributo por defecto.

**Otros lugares que hay que actualizar en conjunto, no solo el prompt de párrafo:**
- `BLUEPRINT.md` — el contrato de formato exacto (`### [Título]` + párrafo + `*(Fuente: ...)*`) debe
  reflejar el nuevo formato sin la línea de fuente.
- `editorial_review.py` — el prompt de revisión (línea 10) valida explícitamente que exista
  `*(Fuente: ...)*`; ese chequeo debe cambiar a validar el hipervínculo en el título en su lugar.
- `CLAUDE.md` — la sección "Key constraints" documenta `*(Fuente: {source})*` como invariante obligatorio;
  actualizar una vez implementado.
- `text_cleaner.strip_markdown()` ya convierte `[texto](url)` → `texto` (línea 9), así que el TTS seguiría
  leyendo solo el título limpio, sin la URL — no requiere cambios.

## Prioridad 4 — Observabilidad: log de errores estructurado

Hoy los `except Exception` en [article_fetcher.py:43](src/article_fetcher.py:43) y
[web_searcher.py:82](src/web_searcher.py:82) tragan la excepción sin registrar tipo/mensaje. Mientras
se corre manualmente esto se tolera (se ve en la terminal), pero en cuanto el pipeline corra desatendido
vía systemd/cron, todo ese detalle se pierde.

**Acción, antes de programar el timer:**
- Loguear `type(e).__name__` y `str(e)` en cada catch, no solo `return None`/`continue`.
- Decidir destino del log: archivo rotado en el proyecto (p. ej. `logs/digest13.log`, gitignored) o
  dejar que systemd capture stdout/stderr en el journal (`journalctl --user -u digest13.service`) — con
  journal alcanza si no se necesita retención larga.
- Si se usa journal, no hace falta un logger dedicado: los `print()` actuales ya van a stdout/stderr, que
  systemd captura automáticamente.

## Prioridad 5 — Confiabilidad: alerta si el run falla o queda vacío

El script corre a las 7am sin supervisión. Si `filter_items()` rechaza todo (`main.py:104-106`) o si
`email_sender.send()` lanza una excepción (SMTP caído, credenciales vencidas), el único síntoma visible
es "no llegó el correo hoy" — que se puede notar horas o días después.

**Acción:**
- Opción simple: unidad `OnFailure=` en systemd que dispare un correo/notificación mínima cuando
  `digest13.service` termine con código de error.
- Opción alternativa sin más infraestructura: revisar `journalctl --user -u digest13.service --since today`
  periódicamente, o agregar un chequeo manual rápido a la rutina matutina hasta tener confianza en el
  pipeline.

## Prioridad 6 — Calidad: deduplicación por título exacto puede dejar pasar duplicados temáticos

`web_searcher.py:68-71` dedupea por título exacto (o primeros 80 caracteres del summary). Como Guardian,
BBC y Al Jazeera cubren el mismo evento con titulares distintos, el mismo hecho puede colarse dos veces
en Geopolítica bajo redacciones distintas — el filtro de relevancia no tiene contexto de que ya vio esa
noticia.

**Acción (solo si se nota en la práctica):** dedup difuso por similitud de título/resumen antes de mandar
los items al filtro de relevancia, o pedirle al LLM de relevancia que marque duplicados temáticos si ve
el resto de titulares del batch.

## Prioridad 7 — Menor: timeout explícito en SMTP

`email_sender.py:26` abre `smtplib.SMTP(SMTP_SERVER, SMTP_PORT)` sin `timeout=`. Si el servidor SMTP
queda colgado, el proceso completo (incluida la limpieza de temporales) se bloquea indefinidamente.
Agregar `timeout=30` o similar cuando se vaya a dejar el pipeline corriendo sin supervisión.

## Prioridad 8 — Menor: reutilización de cliente Groq

`llm.py:16` instancia `Groq(api_key=...)` en cada llamada a `call_llm()`, y hay una llamada por item de
RSS más una por artículo seleccionado — potencialmente 40-60 instanciaciones por run. No es un problema
de correctitud, solo overhead evitable; se puede mover a un cliente módulo-level si se quiere pulir.

## Prioridad 9 — Resiliencia: proveedor LLM de respaldo cuando se agote el presupuesto de Groq

Groq da 200K tokens/día gratis para `openai/gpt-oss-120b`, pero en fases de prueba intensiva ese
presupuesto se agota rápido y el pipeline queda sin poder correr ese día. `call_llm()` en
[llm.py](src/llm.py:10) ya es una capa angosta con firma fija
(`call_llm(system_prompt, user_prompt, max_tokens, temperature) -> str | None`) — ni `relevance.py`,
ni `paragraph_gen.py`, ni `editorial_review.py` conocen el proveedor detrás, solo llaman a esa función.

**Acción:** cuando se quiera un respaldo (p. ej. Gemini, que hoy resulta barato/generoso en su tier),
el cambio queda contenido en `llm.py`: detectar agotamiento del proveedor primario (429 tras agotar
reintentos) y caer a un segundo cliente con la misma firma, o decidir el proveedor por variable de
entorno. No requiere tocar los módulos de prompts.

## Prioridad 10 (la más baja) — Eficiencia: conteo real de tokens en vez de estimación

`main.py:114-148` estima tokens con `len(texto) // 4` y **no cuenta los tokens de la etapa de
relevancia** (un LLM call por cada item de RSS crudo, antes de que `approx_tokens` empiece a acumularse).
La estimación real de consumo puede ser mayor que la visible en el texto de entrada/salida.

**Nota de prioridad:** esto era relevante cuando se pensaba ajustar `TOKEN_LIMIT` con precisión para no
desperdiciar cuota. Dado que la cuota de Groq no es una preocupación para este proyecto (ver contexto
arriba), esto baja a "nice to have" — solo vale la pena si en algún momento se quiere *diagnóstico* de
consumo, no para restringir nada.

**Acción, si se retoma:**
- `call_llm()` en [llm.py](src/llm.py) puede devolver también `response.usage.total_tokens` (Groq lo
  expone) en vez de que cada módulo estime con `len()//4`.
- Acumular ese total real en `main.py`, incluyendo la etapa de `filter_items()`, no solo la de párrafos.

---

**Orden de aplicación:** Prioridad 1 → 2 (bugs con impacto directo en calidad/completitud del
digest, atender primero) → 3 (feature de UX que el usuario quiere pronto) → 4 y 5 (necesarios antes de
dejarlo desatendido) → 6, 7, 8 (pulido opcional) → 9 (si se decide diversificar proveedor) → 10 (solo si se
quiere instrumentación de consumo, no por ahorro).
