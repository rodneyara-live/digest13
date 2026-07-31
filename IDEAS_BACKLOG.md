# Digest 13 — Backlog de ideas (post-iteración)

Recomendaciones para aplicar **cuando el pipeline y el contenido resultante ya estén a gusto** y se
quiera pasar de "modo experimentación" a "servicio desatendido estable". Ordenadas por prioridad —
la lista está pensada para retomarse tanto acá como con cualquier otro agente (p. ej. Big Pickle).

**Contexto de prioridad, importante para no sobre-optimizar lo que no importa:** este es un proyecto
personal de un solo usuario, corriendo sobre la cuota gratuita de Groq (200K tokens/día). El costo de
tokens **no es una preocupación** — lo que importa es la calidad del resultado final (curación, edición,
redacción) y no perder interacciones por límites artificialmente estrechos. Cualquier recomendación que
suene a "ahorrar tokens" debe pesarse contra esto: aquí se prefiere gastar de más a perder una llamada.

---

## Items abiertos

### Prioridad 1 — Observabilidad: log de errores estructurado

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

### Prioridad 2 — Confiabilidad: alerta si el run falla o queda vacío

El script corre a las 7am sin supervisión. Si `filter_items()` rechaza todo (`main.py:104-106`) o si
`email_sender.send()` lanza una excepción (SMTP caído, credenciales vencidas), el único síntoma visible
es "no llegó el correo hoy" — que se puede notar horas o días después.

**Acción:**
- Opción simple: unidad `OnFailure=` en systemd que dispare un correo/notificación mínima cuando
  `digest13.service` termine con código de error.
- Opción alternativa sin más infraestructura: revisar `journalctl --user -u digest13.service --since today`
  periódicamente, o agregar un chequeo manual rápido a la rutina matutina hasta tener confianza en el
  pipeline.

### Prioridad 3 — Calidad: deduplicación por título exacto puede dejar pasar duplicados temáticos

`web_searcher.py:68-71` dedupea por título exacto (o primeros 80 caracteres del summary). Como Guardian,
BBC y Al Jazeera cubren el mismo evento con titulares distintos, el mismo hecho puede colarse dos veces
en Geopolítica bajo redacciones distintas — el filtro de relevancia no tiene contexto de que ya vio esa
noticia.

**Acción (solo si se nota en la práctica):** dedup difuso por similitud de título/resumen antes de mandar
los items al filtro de relevancia, o pedirle al LLM de relevancia que marque duplicados temáticos si ve
el resto de titulares del batch.

### Prioridad 4 — Resiliencia: proveedor LLM de respaldo cuando se agote el presupuesto de Groq

Groq da 200K tokens/día gratis para `openai/gpt-oss-120b`, pero en fases de prueba intensiva ese
presupuesto se agota rápido y el pipeline queda sin poder correr ese día. `call_llm()` en
[llm.py](src/llm.py:10) ya es una capa angosta con firma fija
(`call_llm(system_prompt, user_prompt, max_tokens, temperature) -> str | None`) — ni `relevance.py`,
ni `paragraph_gen.py`, ni `editorial_review.py` conocen el proveedor detrás, solo llaman a esa función.

**Acción:** cuando se quiera un respaldo (p. ej. Gemini, que hoy resulta barato/generoso en su tier),
el cambio queda contenido en `llm.py`: detectar agotamiento del proveedor primario (429 tras agotar
reintentos) y caer a un segundo cliente con la misma firma, o decidir el proveedor por variable de
entorno. No requiere tocar los módulos de prompts.

### Prioridad 5 (la más baja) — Eficiencia: conteo real de tokens en vez de estimación

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

## Items cerrados

### ~~Prioridad original 1 — `max_tokens` demasiado ajustados, riesgo de rechazo silencioso~~

**Cerrado en:** commit `0f0f805` (2026-07-31)

**Evidencia:**
- `src/relevance.py:72` — `max_tokens` subido de 300 → 600.
- `src/paragraph_gen.py:20` — `max_tokens` subido de 600 → 800.
- `src/llm.py:28-30` — instrumentación de `response.choices[0].finish_reason`: si es `"length"`, se imprime `⚠ TRUNCADO: finish_reason=length (max_tokens=N)` en la terminal. Esto permite calibrar con datos reales en vez de suponer.
- `editorial_review.py` — sin cambio, 1500 ya es suficiente.

### ~~Prioridad original 2 — Corrección: descompresión gzip/brotli en `article_fetcher.py`~~

**Cerrado en:** commit `0f0f805` (2026-07-31)

**Evidencia:**
- `src/article_fetcher.py:35` — el bloque manual de gzip (`if content[:2] == b"\x1f\x8b": content = gzip.decompress(content)`) fue reemplazado por `content = _decompress(resp.content)`.
- `_decompress()` (línea 16) ahora se invoca como path real, cubriendo gzip, zlib y brotli con fallback a `raw`. Semanario Universidad debería dejar de fallar con servidores que usen deflate/brotli.

### ~~Prioridad original 3 — Feature: hipervínculo al artículo original en el título H3~~

**Cerrado en:** commit `pendiente` (2026-07-31)

**Evidencia:**
- `src/paragraph_gen.py` — prompt modificado: eliminada línea `*(Fuente: {source})*`. Nuevo post-procesamiento con regex inyecta la URL real del `Item` en el título: `### [título](url)`.
- `src/editorial_review.py:11` — validación cambiada de `### [Título] + párrafo + *(Fuente: ...)*` a `### [Título](url) + párrafo`.
- `BLUEPRINT.md` — Etapa 5 y 6 actualizadas para reflejar el nuevo formato sin línea de fuente.
- `AGENTS.md` — constraint actualizado: `Each news item title is a hyperlink to the original article`.
- `CLAUDE.md` — constraints de formato y párrafo actualizados.
- `text_cleaner.py` — sin cambios necesarios: ya convierte `[texto](url)` → `texto` para TTS.

### ~~Prioridad original 7 — Menor: timeout explícito en SMTP~~

**Cerrado en:** commit `pendiente` (2026-07-31)

**Evidencia:**
- `src/email_sender.py:26` — `smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)`. Evita bloqueo indefinido si el servidor SMTP no responde.

### ~~Prioridad original 8 — Menor: reutilización de cliente Groq~~

**Cerrado en:** commit `pendiente` (2026-07-31)

**Evidencia:**
- `src/llm.py:9-16` — cliente Groq instanciado una sola vez a nivel de módulo via `_get_client()` (lazy init). Antes se creaba uno nuevo en cada llamada (40-60 por run).

---

**Orden de aplicación (para items abiertos):** 1 (log de errores, antes de desatender) → 2 (alerta si falla) → 3 (dedup temático, si se nota en práctica) → 4 (respaldo LLM, si se agota cuota) → 5 (conteo real de tokens, solo diagnóstico).
