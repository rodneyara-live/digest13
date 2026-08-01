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

**Nota:** esto es distinto del split de tres modelos de Groq (`llama-3.1-8b-instant` +
`llama-3.3-70b-versatile` + `openai/gpt-oss-120b`) ya implementado — ese reparte la carga entre cuotas
*dentro* de Groq. Este ítem es para cuando **todas** las cuotas de Groq se agoten el mismo día y se
necesite un proveedor externo distinto (p. ej. Gemini) como respaldo total.

**Prioridad revisada a la baja:** con el routing por etapa (relevancia/dedup en la cuota de 500K,
párrafos en la de 100K usando solo ~14K), agotar las tres cuotas el mismo día pasó a requerir un orden
de magnitud más de corridas que antes. Sigue siendo la resiliencia correcta a largo plazo, pero ya no
es una restricción que se toque en operación normal.

Groq da 100K-200K tokens/día gratis por modelo, pero en fases de prueba intensiva ambos presupuestos se
pueden agotar el mismo día y el pipeline queda sin poder correr. `call_llm()` en
[llm.py](src/llm.py:10) ya es una capa angosta con firma fija
(`call_llm(system_prompt, user_prompt, max_tokens, temperature) -> str | None`) — ni `relevance.py`,
ni `paragraph_gen.py`, ni `editorial_review.py` conocen el proveedor detrás, solo llaman a esa función.

**Acción:** cuando se quiera un respaldo (p. ej. Gemini, que hoy resulta barato/generoso en su tier),
el cambio queda contenido en `llm.py`: detectar agotamiento del proveedor primario (429 tras agotar
reintentos) y caer a un segundo cliente con la misma firma, o decidir el proveedor por variable de
entorno. No requiere tocar los módulos de prompts.

### Prioridad 2 — Eficiencia: agrupar el filtro de relevancia en lotes

**Diferido a propósito, no pendiente por olvido.** Hoy funciona bien item por item y una corrida limpia
cabe cómodamente en las cuotas; no se toca lo que no está roto. Esta entrada existe para que la decisión
se pueda re-evaluar con los números a mano en vez de re-investigarla.

**Situación:** `filter_items()` en [relevance.py](src/relevance.py:63) hace **una llamada LLM por item**
(~44/día) y reenvía la lista completa de criterios de rechazo en cada una. Medido: ~34K tokens, el ~65%
del gasto total de la corrida (~52K). Agrupar en lotes de 10 lo bajaría a ~5 llamadas y ~14K tokens —
suficiente para que *todo* el pipeline de volumen (relevancia + dedup + párrafos) quepa en la cuota de
100K de `llama-3.3-70b-versatile` con ~3x de margen, es decir: el ahorro no es para gastar menos, es lo
que haría *asequible* usar el modelo bueno también para clasificar.

**Contras que motivaron el diferimiento:**
- Implica reescribir el prompt de relevancia, que `BLUEPRINT.md` marca como verbatim/afinado (habría que
  actualizar BLUEPRINT.md, CLAUDE.md y AGENTS.md junto con el cambio).
- Duda razonable sobre si un modelo de 8B mantiene el criterio de forma consistente a lo largo de un lote
  grande, cuando hoy item por item lo hace bien.
- Un lote malo cuesta 10 noticias en vez de 1.

**Si se evalúa:** numerar los items con ID y parsear por ID, con **reintento individual** de los IDs que
el modelo omita — así un lote incompleto degrada a llamadas sueltas en vez de perder el lote. Conservar
la distinción `MALFORMADO` vs `RECHAZADO` que ya existe ([relevance.py:86](src/relevance.py:86)), que es
justo la salvaguarda que detectaría un lote mal formado. Un tamaño de lote de 5 es la variante
conservadora (~9 llamadas, ~20K tokens).

### ~~Calibración: etapa 1 y etapa 6 no coinciden en qué es "tema válido"~~ (resuelto — era el recorte)

**Diagnóstico inicial equivocado, se documenta para no repetirlo.** Al arreglar el gate editorial (que
fallaba abierto por markdown en el veredicto) apareció lo que parecía un desacuerdo de criterio entre
etapas: en la corrida del 2026-08-01 12:48 el editor rechazó el digest completo alegando noticias fuera
de "geopolítica/CR/tech", contenido que la etapa 1 había aprobado como MUNDO. La conclusión tentativa fue
degradar ese criterio de RECHAZO a CORRECCIÓN.

**Era un síntoma.** La causa real: `review()` recortaba el informe a 8000 caracteres y un digest de 15
noticias ocupa ~12.5K, así que el editor juzgaba solo los primeros dos tercios — donde estaban justo las
dos noticias discutibles. La proporción de contenido fuera de tema le parecía 2 de 9 en vez de 2 de 14, y
además el corte caía a mitad de una URL, lo que le hacía reportar defectos inexistentes. Con
`MAX_REVIEW_CHARS = 24000` y recorte en frontera de noticia, el mismo digest se **aprueba** (verificado dos
veces seguidas sobre el texto exacto que se había enviado).

**Lección para el futuro:** antes de aflojar un criterio del prompt editorial, verificar qué porción del
informe está viendo realmente el modelo. Degradar el criterio habría debilitado el gate de forma permanente
para tapar un bug de truncamiento.

### Prioridad 3 — Calidad: caché entre corridas (SQLite, 3-7 días)

**Diferido junto con el anterior**, pero es sobre todo una mejora de *calidad*, no de gasto.

**Situación:** el pipeline no tiene estado entre corridas. Con `MAX_AGE_HOURS = 48` en
[web_searcher.py](src/web_searcher.py:44) y ejecución diaria, los items de ayer se vuelven a evaluar hoy
—se re-paga la llamada de relevancia por algo ya juzgado— y, más importante, **nada impide que la misma
noticia salga en el digest dos días seguidos**. El riesgo se concentra en COSTA RICA: solo 2 feeds,
Semanario Universidad es un semanario (sus items persisten días en el feed) y `select_by_quota()` fuerza
un `min: 3` para esa sección, así que si hay poco material nuevo el relleno viene de lo ya publicado.

**Acción:** SQLite en `.cache/` (ya está en `.gitignore`), `url → (puntaje, sección, fecha, ya_publicado)`
con TTL de 3 a 7 días. Dos usos: excluir de la selección lo ya publicado, y reutilizar el puntaje en vez
de volver a preguntar. Se puede implementar solo la primera mitad (excluir repetidos) si se prefiere no
cachear juicios del LLM que podrían quedar obsoletos al cambiar los prompts.

---

## Items cerrados

### ~~Deliverability: correos van a spam por mismatch FROM/SMTP~~

**Cerrado en:** commit `bfbd455` (2026-08-01)

**Problema:** los correos enviados desde Brevo con remitente `@live.com` iban a spam porque el dominio gratuito no puede autenticarse con SPF/DKIM/DMARC. Microsoft rechaza o marca como spam cualquier correo FROM `@live.com` que no venga de sus propios servidores.

**Solución:** usar Gmail SMTP directo (`smtp.gmail.com`). El FROM y el SMTP son del mismo proveedor → sin mismatch → deliverability perfecta.

**Evidencia:**
- `.env` — configurado con `SMTP_SERVER="smtp.gmail.com"`, `SMTP_USERNAME="rodneyara@gmail.com"`, app password con espacios.
- `.env.example` — documentado Gmail como Opción A, Brevo como Opción B.
- `BLUEPRINT.md` — sección SMTP actualizada con tabla comparativa Gmail vs Brevo.
- Test manual exitoso: correo entregado tanto a `rodneyara@gmail.com` como a `rodneyara@live.com`.

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

**Cerrado en:** commit `d14a7b8` (2026-07-31)

**Evidencia:**
- `src/article_fetcher.py:41-42` — `except Exception as e: print(f"  ERROR [{type(e).__name__}]: {e} — {url[:60]}")`
- `src/web_searcher.py:82-83` — `except Exception as e: print(f"  ERROR [{type(e).__name__}]: {e} — {url[:60]}")`
- Los errores se imprimen a stderr y son capturados por el journal de systemd (`journalctl --user -u digest13.service`).

### ~~Prioridad original 2 (nueva) — Confiabilidad: alerta si el run falla o queda vacío~~

**Cerrado en:** commit `d14a7b8` (2026-07-31)

**Evidencia:**
- `src/main.py` — `sys.exit(1)` en los puntos de fallo crítico (filtro vacío, sin noticias generadas).
- `on-failure.sh` — script que registra fallos en `logs/failures.log` (gitignored).
- `BLUEPRINT.md` — documentación completa de configuración systemd con `OnFailure=digest13-notify.service`.
- La implementación de systemd queda pendiente hasta que se configure el timer; el script funciona standalone con `./on-failure.sh $?`.

### ~~Prioridad original 3 (nueva) — Calidad: deduplicación por título exacto puede dejar pasar duplicados temáticos~~

**Cerrado en:** commit `85b4163` (2026-07-31)

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
- **Nota importante (resuelta, ver ítem siguiente):** la corrida real reveló exactamente el riesgo que
  esta nota anticipaba — un modelo que no sigue el formato esperado colapsaba el filtro de relevancia sin
  que nada lo distinguiera de un día real de pocas noticias.

### ~~Robustez: respuestas malformadas del LLM se contaban como rechazo editorial, sin piso mínimo antes de enviar~~

**Cerrado en:** revisión posterior a `88a3b1b` (2026-08-01), sin gastar cuota de Groq — cambios de
parseo/constantes verificados por lectura, no por corrida.

**Problema (evidencia real, no hipotética):** `logs/digest13.log` — corrida `2026-08-01 09:43:29` con un
modelo distinto al default en `LLM_MODEL`: de 48 items RSS solo 1 fue aprobado, y aun así `main.py` generó
y envió el correo con un solo ítem. Causa raíz en `relevance.py`: `_parse_action()` devolvía `"RECHAZAR"`
por defecto cuando no encontraba una línea `ACCIÓN:` parseable, y `_parse_score()` devolvía `0` cuando no
encontraba `PUNTAJE:` — ambos casos se veían idénticos a un rechazo editorial legítimo en el log. Además,
nada en `main.py` ponía un piso al tamaño final del digest antes de enviarlo.

**Solución:**
- `src/relevance.py` — `_parse_action()`/`_parse_score()` ahora devuelven `None` (no un default de
  rechazo) cuando no encuentran su línea. `filter_items()` cuenta esos casos como `MALFORMADO`
  (log distinto de `RECHAZADO`) y al final imprime `⚠ N/M respuestas malformadas` si el modelo no está
  siguiendo el formato.
- `src/main.py` — nueva constante `MIN_ITEMS_FOR_DIGEST = 5`; el chequeo que antes solo abortaba con
  `paragraphs` vacío ahora aborta (`sys.exit(1)`, sin enviar correo) si el conteo final queda por debajo
  de ese piso, no solo en cero.
- `BLUEPRINT.md`, `CLAUDE.md`, `AGENTS.md` — documentado el comportamiento `MALFORMADO` y el piso mínimo.

### ~~Eficiencia: conteo real de tokens en vez de estimación~~

**Cerrado en:** commit `9e991c7` (2026-07-31)

**Evidencia:**
- `src/llm.py` — `get_token_usage()` expone `response.usage.total_tokens` de Groq en cada llamada.
- `src/main.py` — `_write_run_log()` escribe resumen a `logs/digest13.log` con tokens reales por modelo.
- La estimación con `len()//4` fue eliminada; ahora se usa el conteo real de la API.

---

**Orden de aplicación (para items abiertos):** 1 (respaldo LLM, si se agota cuota) → 2 (conteo real de tokens, solo diagnóstico).
