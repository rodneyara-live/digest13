import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.audio import MIMEAudio
from config import *


def send(html_content: str, audio_bytes: bytes, date_stamp: str) -> None:
    mp3_filename = f"digest13.{date_stamp}.mp3"

    msg = MIMEMultipart("related")
    msg["Subject"] = f"Digest 13 - Informe Diario - {date_stamp}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    msg_alt = MIMEMultipart("alternative")
    msg.attach(msg_alt)

    msg_alt.attach(MIMEText(html_content, "html", "utf-8"))

    audio_part = MIMEAudio(audio_bytes, _subtype="mpeg")
    audio_part.add_header("Content-Disposition", "inline", filename=mp3_filename)
    audio_part.add_header("Content-ID", "<audio_resumen_mp3>")
    msg.attach(audio_part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)


def send_failure_alert(subject: str, error_text: str) -> None:
    import html
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    escaped_text = html.escape(error_text)
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #24292e; line-height: 1.5; padding: 20px; background-color: #f6f8fa;">
  <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border: 1px solid #d1d5da; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
    <div style="background-color: #d73a49; color: white; padding: 16px 20px;">
      <h2 style="margin: 0; font-size: 18px; font-weight: 600;">⚠️ Fallo en Digest 13</h2>
    </div>
    <div style="padding: 24px 20px;">
      <p style="margin-top: 0;">Se produjo un error al ejecutar el generador diario de <strong>Digest 13</strong> y el resumen no pudo ser completado.</p>
      <h3 style="font-size: 14px; color: #586069; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 20px; margin-bottom: 8px;">Detalle del error y últimos registros:</h3>
      <pre style="background: #24292e; color: #f6f8fa; padding: 14px; border-radius: 6px; overflow-x: auto; font-size: 12px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; white-space: pre-wrap; word-break: break-word; line-height: 1.4;">{escaped_text}</pre>
    </div>
    <div style="background-color: #f6f8fa; border-top: 1px solid #eaecef; padding: 12px 20px; font-size: 12px; color: #586069;">
      Servicio Digest 13 • Alerta automática de fallos
    </div>
  </div>
</body>
</html>"""

    msg.attach(MIMEText(error_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)

