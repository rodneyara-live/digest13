import asyncio
from pathlib import Path
from config import PROJECT_ROOT
from llm_client import generate_news
from html_generator import build_html
from tts_engine import synthesize
from email_sender import send


def main() -> None:
    print("Generando noticias...")
    news_text = generate_news()

    html_path = PROJECT_ROOT / "digest13.html"
    print("Construyendo HTML...")
    html_content = build_html(news_text, html_path)

    mp3_path = PROJECT_ROOT / "resumen.mp3"
    print("Sintetizando audio...")
    audio_bytes = asyncio.run(synthesize(news_text, mp3_path))

    print("Enviando correo electrónico...")
    send(html_content, audio_bytes)

    print("¡Listo! Digest 13 entregado.")


if __name__ == "__main__":
    main()
