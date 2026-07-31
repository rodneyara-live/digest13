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
