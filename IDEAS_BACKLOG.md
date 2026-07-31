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

### Prioridad 1 — Resiliencia: proveedor LLM de respaldo cuando se agote el presupuesto de Groq

**Nota:** esto es distinto del split de dos modelos de Groq (`llama-3.3-70b-versatile` +
`openai/gpt-oss-120b`) ya implementado — ese reparte la carga entre dos cuotas *dentro* de Groq. Este
ítem es para cuando **ambas** cuotas de Groq se agoten el mismo día y se necesite un proveedor externo
distinto (p. ej. Gemini) como respaldo total.

Groq da 100K-200K tokens/día gratis por modelo, pero en fases de prueba intensiva ambos presupuestos se
pueden agotar el mismo día y el pipeline queda sin poder correr. `call_llm()` en
[llm.py](src/llm.py:10) ya es una capa angosta con firma fija
(`call_llm(system_prompt, user_prompt, max_tokens, temperature) -> str | None`) — ni `relevance.py`,
ni `paragraph_gen.py`, ni `editorial_review.py` conocen el proveedor detrás, solo llaman a esa función.

**Acción:** cuando se quiera un respaldo (p. ej. Gemini, que hoy resulta barato/generoso en su tier),
el cambio queda contenido en `llm.py`: detectar agotamiento del proveedor primario (429 tras agotar
reintentos) y caer a un segundo cliente con la misma firma, o decidir el proveedor por variable de
entorno. No requiere tocar los módulos de prompts.

### Prioridad 2 (la más baja) — Eficiencia: conteo real de tokens en vez de estimación

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

**Cerrado en:** commit `a7b6b0f` (2026-07-31); **regresión encontrada y corregida en revisión posterior** (sin
correr el pipeline — se verificó localmente con `markdown.markdown()` sobre casos simulados, sin gastar
cuota de Groq).

**Evidencia:**
- `src/paragraph_gen.py` — prompt modificado: eliminada línea `*(Fuente: {source})*`. Nuevo post-procesamiento con regex inyecta la URL real del `Item` en el título: `### [título](url)`.
- `src/editorial_review.py:11` — validación cambiada de `### [Título] + párrafo + *(Fuente: ...)*` a `### [Título](url) + párrafo`.
- `BLUEPRINT.md` — Etapa 5 y 6 actualizadas para reflejar el nuevo formato sin línea de fuente.
- `AGENTS.md` — constraint actualizado: `Each news item title is a hyperlink to the original article`.
- `CLAUDE.md` — constraints de formato y párrafo actualizados.
- `text_cleaner.py` — sin cambios necesarios: ya convierte `[texto](url)` → `texto` para TTS.
- **Bug encontrado:** la regex original (`^###\s+(.+)$`) asumía que el título capturado no traía corchetes
  propios. Como el prompt le muestra al modelo el formato `### [Título descriptivo y directo]` — con
  corchetes incluidos en el ejemplo — es muy probable que el modelo los reproduzca literalmente, dando
  `### [[Título]](url)`. Verificado con `markdown.markdown()`: el enlace queda funcional, pero el texto
  visible del `<h3>` sale como `[Título]`, con corchetes literales — visible en cada noticia del digest.
  **Fix aplicado:** regex cambiada a `^###\s*\[?(.+?)\]?\s*$`, que tolera corchetes opcionales del modelo
  y siempre reconstruye con exactamente un par. Verificado con ambos casos (con y sin corchetes del
  modelo) dando el mismo resultado limpio.

### ~~Prioridad original 7 — Menor: timeout explícito en SMTP~~

**Cerrado en:** commit `a7b6b0f` (2026-07-31)

**Evidencia:**
- `src/email_sender.py:26` — `smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)`. Evita bloqueo indefinido si el servidor SMTP no responde.

### ~~Prioridad original 8 — Menor: reutilización de cliente Groq~~

**Cerrado en:** commit `a7b6b0f` (2026-07-31)

**Evidencia:**
- `src/llm.py:9-16` — cliente Groq instanciado una sola vez a nivel de módulo via `_get_client()` (lazy init). Antes se creaba uno nuevo en cada llamada (40-60 por run).

### ~~Prioridad original 1 (nueva) — Observabilidad: log de errores estructurado~~

**Cerrado en:** commit `pendiente` (2026-07-31)

**Evidencia:**
- `src/article_fetcher.py:41-42` — `except Exception as e: print(f"  ERROR [{type(e).__name__}]: {e} — {url[:60]}")`
- `src/web_searcher.py:82-83` — `except Exception as e: print(f"  ERROR [{type(e).__name__}]: {e} — {url[:60]}")`
- Los errores se imprimen a stderr y son capturados por el journal de systemd (`journalctl --user -u digest13.service`).

### ~~Prioridad original 2 (nueva) — Confiabilidad: alerta si el run falla o queda vacío~~

**Cerrado en:** commit `pendiente` (2026-07-31)

**Evidencia:**
- `src/main.py` — `sys.exit(1)` en los puntos de fallo crítico (filtro vacío, sin noticias generadas).
- `on-failure.sh` — script que registra fallos en `logs/failures.log` (gitignored).
- `BLUEPRINT.md` — documentación completa de configuración systemd con `OnFailure=digest13-notify.service`.
- La implementación de systemd queda pendiente hasta que se configure el timer; el script funciona standalone con `./on-failure.sh $?`.

### ~~Prioridad original 3 (nueva) — Calidad: deduplicación por título exacto puede dejar pasar duplicados temáticos~~

**Cerrado en:** commit `pendiente` (2026-07-31)

**Evidencia:**
- `src/relevance.py:126-167` — `deduplicate_by_event()`: una llamada LLM agrupa los top-20 items por el mismo evento. Se conserva el de mayor puntaje de cada grupo.
- `src/main.py:68-74` — `_is_duplicate()`: dedup determinista por similitud de keywords (umbral 0.65) durante `select_by_quota()`.
- Estos dos mecanismos cubren el caso original del backlog (Guardian + BBC cubriendo el mismo evento con distinto titular). Falta verificación en producción para confirmar que no pasan duplicados.

### ~~Consistencia — `deduplicate_by_event()` reincidía en el mismo problema de `max_tokens` ajustado~~

**Cerrado en:** revisión posterior a `85b4163` (sin correr el pipeline; cambio de una constante, sin
necesidad de probar contra Groq).

**Evidencia:**
- `src/relevance.py` — `deduplicate_by_event()` usaba `max_tokens=300`, el mismo valor que se acababa de
  identificar como insuficiente para el modelo reasoning en `relevance.py`'s `filter_items()`. Subido a
  600 para ser consistente con el criterio ya establecido en la Prioridad original 1.

### ~~Nueva — Arquitectura de dos modelos Groq: volumen con `llama-3.3-70b-versatile`, revisión editorial con `gpt-oss-120b`~~

**Cerrado en:** revisión posterior a `85b4163` (sin correr el pipeline; cambio de default de env var,
requiere verificarse en la próxima corrida real).

Esto no estaba en el backlog original como ítem propio, pero surgió de una inconsistencia real detectada
en revisión: `BLUEPRINT.md` ya describía este split de dos modelos en un párrafo, pero **se contradecía
con el resto del mismo documento** (que decía `gpt-oss-120b` para todo) y con `config.py`/`.env.example`
(que también defaulteaban todo a `gpt-oss-120b`). El usuario confirmó que el split de dos modelos sí es
el diseño querido — no solo una corrección de documentación, sino una funcionalidad que faltaba terminar
de implementar.

**Evidencia:**
- `src/config.py` — `LLM_MODEL` default cambiado de `openai/gpt-oss-120b` → `llama-3.3-70b-versatile`.
  `EDITORIAL_MODEL` se mantiene en `openai/gpt-oss-120b`.
- `.env.example` — mismo cambio, con comentario explicando el porqué del split (dos cuotas diarias
  independientes: 100K/día para `llama-3.3-70b-versatile`, 200K/día para `gpt-oss-120b`).
- `BLUEPRINT.md` — reconciliado en todos los lugares donde se mencionaba el modelo (diagrama, requisitos,
  ejemplo de `.env`, tabla nueva en "Pipeline de Curación" con `max_tokens` por etapa) para que no haya
  ninguna contradicción interna.
- `AGENTS.md` y `CLAUDE.md` — actualizados como versiones simplificadas consistentes con `BLUEPRINT.md`;
  también se agregó la documentación de la etapa de dedup (`deduplicate_by_event`, `_is_duplicate`) que
  faltaba en ambos desde que se implementó en `85b4163`.
- **Nota importante:** no se pudo correr el pipeline para confirmar que `llama-3.3-70b-versatile` sigue
  produciendo el formato esperado (`PUNTAJE:`/`ACCIÓN:`/`SECCIÓN:`/`MOTIVO:` en relevancia, título+párrafo
  en la generación) — al ser un modelo distinto al que se usó para afinar esos prompts, conviene revisar
  la primera corrida real con atención antes de asumir que el comportamiento es idéntico.

---

**Orden de aplicación (para items abiertos):** 1 (respaldo LLM, si se agota cuota) → 2 (conteo real de tokens, solo diagnóstico).
