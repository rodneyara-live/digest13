import trafilatura


def fetch_full_text(url: str) -> str | None:
    if not url:
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded)
        if text and len(text.strip()) > 100:
            return text.strip()
        return None
    except Exception:
        return None
