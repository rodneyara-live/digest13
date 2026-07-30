# 📰 Digest 13

Pipeline automatizado de generación de noticias diarias: consulta Groq (LLaMA 3.3 70B), maqueta un informe en HTML, sintetiza audio con `edge-tts` y envía el paquete por correo electrónico.

## Requisitos

- Python 3.10+
- API key de [Groq](https://console.groq.com)
- Cuenta SMTP para envío de correos

## Instalación

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # completar GROQ_API_KEY, SMTP_*, EMAIL_*, TTS_VOICE
```

## Uso

### Manual

```bash
python src/main.py
```

### Automático (systemd)

Instalar los units en `~/.config/systemd/user/`:

```bash
systemctl --user daemon-reload
systemctl --user enable --now digest13.timer
```

Ejecuta el pipeline cada día a las 7:00 AM. Con `Persistent=true` ejecuta tareas atrasadas al encender el equipo.

## Estructura

```
src/
├── main.py            # entrada del pipeline
├── config.py          # entorno y direccionamiento de caché
├── llm_client.py      # consulta a Groq (LLaMA 3.3 70B)
├── html_generator.py  # plantilla HTML con audio embebido
├── tts_engine.py      # síntesis de voz con edge-tts
└── email_sender.py    # ensamblado MIME y envío SMTP
```

## Licencia

Sin definir.
