import feedparser
from dataclasses import dataclass, field


@dataclass
class Item:
    section: str
    title: str
    source: str
    url: str
    summary: str


SOURCE_MAP: dict[str, str] = {
    "theguardian.com": "The Guardian",
    "bbc.co.uk": "BBC News",
    "aljazeera.com": "Al Jazeera",
    "delfino.cr": "Delfino.cr",
    "semanariouniversidad.com": "Semanario Universidad",
    "arstechnica.com": "Ars Technica",
}

FEEDS: list[tuple[str, list[str]]] = [
    ("GEOPOLÍTICA Y AMÉRICA LATINA", [
        "https://www.theguardian.com/world/rss",
        "https://www.theguardian.com/world/americas/rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ]),
    ("POLÍTICA Y SOCIEDAD COSTARRICENSE", [
        "https://delfino.cr/feed",
        "https://semanariouniversidad.com/feed",
    ]),
    ("TECNOLOGÍA, INFRAESTRUCTURA Y SOFTWARE", [
        "https://www.theguardian.com/technology/rss",
        "https://feeds.arstechnica.com/arstechnica/index",
    ]),
]

MAX_PER_FEED = 6


def _source_name(url: str) -> str:
    for domain, name in SOURCE_MAP.items():
        if domain in url:
            return name
    return url.split("//")[1].split("/")[0]


def fetch_items() -> list[Item]:
    items: list[Item] = []
    seen: set[str] = set()

    for section_name, urls in FEEDS:
        for url in urls:
            try:
                feed = feedparser.parse(url)
                source = _source_name(url)
                count = 0
                for entry in feed.entries:
                    title = (entry.get("title") or "").strip()
                    summary = (entry.get("summary") or entry.get("description") or "").strip()
                    link = entry.get("link") or ""
                    if not title and not summary:
                        continue
                    key = title or summary[:80]
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(Item(
                        section=section_name,
                        title=title,
                        source=source,
                        url=link,
                        summary=summary[:500],
                    ))
                    count += 1
                    if count >= MAX_PER_FEED:
                        break
            except Exception:
                continue

    return items
