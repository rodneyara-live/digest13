# Digest 13 — Backlog de ideas (post-iteración)

Recomendaciones para aplicar **cuando el pipeline y el contenido resultante ya estén a gusto** y se
quiera pasar de "modo experimentación" a "servicio desatendido estable". No son urgentes mientras se
siga iterando sobre calidad de prompts/secciones/fuentes.

## 1. Corrección — descompresión gzip/brotli en `article_fetcher.py`

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

## 2. Observabilidad — log de errores estructurado

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

## 3. Confiabilidad — alerta si el run falla o queda vacío

El script corre a las 7am sin supervisión. Si `filter_items()` rechaza todo (`main.py:104-106`) o si
`email_sender.send()` lanza una excepción (SMTP caído, credenciales vencidas), el único síntoma visible
es "no llegó el correo hoy" — que se puede notar horas o días después.

**Acción:**
- Opción simple: unidad `OnFailure=` en systemd que dispare un correo/notificación mínima cuando
  `digest13.service` termine con código de error.
- Opción alternativa sin más infraestructura: revisar `journalctl --user -u digest13.service --since today`
  periódicamente, o agregar un chequeo manual rápido a la rutina matutina hasta tener confianza en el
  pipeline.

## 4. Eficiencia — conteo real de tokens en vez de estimación

`main.py:114-148` estima tokens con `len(texto) // 4` y **no cuenta los tokens de la etapa de
relevancia** (un LLM call por cada item de RSS crudo, antes de que `approx_tokens` empiece a acumularse).
Como el modelo es *reasoning* y quema tokens en chain-of-thought oculto, la estimación real de consumo
puede ser bastante mayor que la visible en el texto de entrada/salida.

**Acción, cuando se quiera ajustar el presupuesto diario con precisión:**
- `call_llm()` en [llm.py](src/llm.py) puede devolver también `response.usage.total_tokens` (Groq lo
  expone) en vez de que cada módulo estime con `len()//4`.
- Acumular ese total real en `main.py`, incluyendo la etapa de `filter_items()`, no solo la de párrafos.
- Con eso se puede ajustar `TOKEN_LIMIT` con datos reales en vez de una estimación conservadora a ciegas.

No es urgente mientras el proyecto viva en el tier gratuito y las pruebas repetidas ya se asuman como
sobreconsumo esperado.

## 5. Calidad — deduplicación por título exacto puede dejar pasar duplicados temáticos

`web_searcher.py:68-71` dedupea por título exacto (o primeros 80 caracteres del summary). Como Guardian,
BBC y Al Jazeera cubren el mismo evento con titulares distintos, el mismo hecho puede colarse dos veces
en Geopolítica bajo redacciones distintas — el filtro de relevancia no tiene contexto de que ya vio esa
noticia.

**Acción (opcional, solo si se nota en la práctica):** dedup difuso por similitud de título/resumen antes
de mandar los items al filtro de relevancia, o pedirle al LLM de relevancia que marque duplicados
temáticos si ve el resto de titulares del batch.

## 6. Menor — timeout explícito en SMTP

`email_sender.py:26` abre `smtplib.SMTP(SMTP_SERVER, SMTP_PORT)` sin `timeout=`. Si el servidor SMTP
queda colgado, el proceso completo (incluida la limpieza de temporales) se bloquea indefinidamente.
Agregar `timeout=30` o similar cuando se vaya a dejar el pipeline corriendo sin supervisión.

## 7. Menor — reutilización de cliente Groq

`llm.py:16` instancia `Groq(api_key=...)` en cada llamada a `call_llm()`, y hay una llamada por item de
RSS más una por artículo seleccionado — potencialmente 40-60 instanciaciones por run. No es un problema
de correctitud, solo overhead evitable; se puede mover a un cliente módulo-level si se quiere pulir.

## 8. Resiliencia — proveedor LLM de respaldo cuando se agote el presupuesto de Groq

Groq da 200K tokens/día gratis para `openai/gpt-oss-120b`, pero en fases de prueba intensiva ese
presupuesto se agota rápido y el pipeline queda sin poder correr ese día. `call_llm()` en
[llm.py](src/llm.py:10) ya es una capa angosta con firma fija
(`call_llm(system_prompt, user_prompt, max_tokens, temperature) -> str | None`) — ni `relevance.py`,
ni `paragraph_gen.py`, ni `editorial_review.py` conocen el proveedor detrás, solo llaman a esa función.

**Acción:** cuando se quiera un respaldo (p. ej. Gemini, que hoy resulta barato/generoso en su tier),
el cambio queda contenido en `llm.py`: detectar agotamiento del proveedor primario (429 tras agotar
reintentos) y caer a un segundo cliente con la misma firma, o decidir el proveedor por variable de
entorno. No requiere tocar los módulos de prompts.

---

**Orden sugerido de aplicación cuando llegue el momento:** #1 (bug real, ya identificado) → #2 y #3
(necesarios antes de dejarlo desatendido) → #4 (una vez que el volumen de pruebas baje y se quiera medir
consumo real) → #5, #6, #7 (pulido opcional) → #8 (si se decide diversificar proveedor).
