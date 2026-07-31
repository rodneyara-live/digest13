import gzip
import zlib
import brotli
import trafilatura
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "es-CR,es;q=0.9,en;q=0.8",
}


def _decompress(raw: bytes) -> bytes:
    if raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    try:
        return zlib.decompress(raw)
    except Exception:
        pass
    try:
        return brotli.decompress(raw)
    except Exception:
        return raw


def fetch_full_text(url: str) -> str | None:
    if not url:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        content = resp.content
        if content[:2] == b"\x1f\x8b":
            content = gzip.decompress(content)
        html = content.decode("utf-8", errors="replace")
        text = trafilatura.extract(html)
        if text and len(text.strip()) > 100:
            return text.strip()
        return None
    except Exception:
        return None
