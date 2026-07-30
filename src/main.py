import asyncio
from datetime import date
from pathlib import Path
from config import PROJECT_ROOT
from llm_client import generate_news
from html_generator import build_html
from text_cleaner import strip_markdown
from tts_engine import synthesize
from email_sender import send

DATE_STAMP = date.today().strftime("%Y.%m.%d")
MP3_FILENAME = f"digest13.{DATE_STAMP}.mp3"
HTML_FILENAME = f"digest13.{DATE_STAMP}.html"


def main() -> None:
    print("Generando noticias...")
    news_text = generate_news()

    html_path = PROJECT_ROOT / HTML_FILENAME
    print("Construyendo HTML...")
    html_content = build_html(news_text, html_path)

    mp3_path = PROJECT_ROOT / MP3_FILENAME
    tts_text = strip_markdown(news_text)
    print("Sintetizando audio...")
    audio_bytes = asyncio.run(synthesize(tts_text, mp3_path))

    print("Enviando correo electrónico...")
    send(html_content, audio_bytes, DATE_STAMP)

    print("Limpiando archivos temporales...")
    mp3_path.unlink(missing_ok=True)
    html_path.unlink(missing_ok=True)

    print("¡Listo! Digest 13 entregado.")


if __name__ == "__main__":
    main()
