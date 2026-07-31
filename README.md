# 📰 Digest 13

Pipeline automatizado de noticias diarias: recolecta titulares vía RSS, cura con LLM de razonamiento (puntaje 1-5 + cuotas por sección), maqueta un informe HTML con fuentes citadas, sintetiza audio con `edge-tts` y envía el paquete por correo electrónico.

## Cómo funciona

1. **RSS** — 6 fuentes (The Guardian, BBC, Al Jazeera, Delfino.cr, Semanario Universidad, Ars Technica) por sección.
2. **Filtro de relevancia** — el LLM puntúa cada item de 1 a 5 (5 = imperdible, 1 = rechazar) y lo reasigna a una sección.
3. **Selección por cuotas** — Costa Rica: mín 3 / máx 5; Geopolítica: máx 6; Tecnología: máx 5. Total máx 15 items (~10-12 min de audio).
4. **Párrafos** — descarga del artículo completo (requests + trafilatura con descompresión gzip) y generación con estructura HECHO + CONTEXTO + IMPLICACIÓN.
5. **Revisión editorial** — segunda pasada LLM que valida estructura y calidad.
6. **Entrega** — HTML con audio embebido (`cid:audio_resumen_mp3`) vía SMTP.

## Fuentes RSS

| Sección | Fuentes |
|---------|---------|
| Geopolítica y América Latina | The Guardian, BBC News, Al Jazeera |
| Política y Sociedad Costarricense | Delfino.cr, Semanario Universidad |
| Tecnología, Infraestructura y Software | The Guardian, Ars Technica |

## Requisitos

- Python 3.10+
- API key de [Groq](https://console.groq.com) (gratuita, 200K tokens/día para `openai/gpt-oss-120b`)
- Cuenta SMTP para envío de correos

## Instalación

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # completar GROQ_API_KEY, SMTP_*, EMAIL_*, TTS_VOICE
```

## Uso

```bash
python src/main.py
```

## Estructura

```
src/
├── main.py              # orquestador del pipeline + selección por cuotas
├── config.py            # entorno y direccionamiento de caché
├── web_searcher.py      # agregador de feeds RSS por sección
├── relevance.py         # filtro LLM con puntaje 1-5 por item
├── article_fetcher.py   # descarga con requests + descompresión gzip
├── paragraph_gen.py     # generación de párrafos (HECHO+CONTEXTO+IMPLICACIÓN)
├── editorial_review.py  # revisión editorial de segunda pasada
├── llm.py               # cliente Groq con reintentos en 429
├── text_cleaner.py      # limpia markdown antes de TTS
├── html_generator.py    # plantilla HTML con audio embebido
├── tts_engine.py        # síntesis de voz con edge-tts
└── email_sender.py      # ensamblado MIME y envío SMTP
```

## Licencia

Sin definir.
