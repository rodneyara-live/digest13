# 📰 Digest 13

Pipeline automatizado de generación de noticias diarias: recolecta titulares vía RSS, consulta Groq (LLaMA 3.3 70B), maqueta un informe en HTML con fuentes citadas, sintetiza audio con `edge-tts` y envía el paquete por correo electrónico.

## Fuentes RSS

| Sección | Fuentes |
|---------|---------|
| Geopolítica y América Latina | The Guardian, BBC News, Al Jazeera |
| Política y Sociedad Costarricense | Delfino.cr, Semanario Universidad |
| Tecnología y Cultura Digital | The Guardian, Ars Technica |

## Requisitos

- Python 3.10+
- API key de [Groq](https://console.groq.com) (gratuita)
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
├── main.py            # orquestador del pipeline
├── config.py          # entorno y direccionamiento de caché
├── web_searcher.py    # agregador de feeds RSS por sección
├── llm_client.py      # consulta a Groq con prompt + contexto RSS
├── text_cleaner.py    # limpia markdown antes de TTS
├── html_generator.py  # plantilla HTML con audio embebido
├── tts_engine.py      # síntesis de voz con edge-tts
└── email_sender.py    # ensamblado MIME y envío SMTP
```

## Licencia

Sin definir.
