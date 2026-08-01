import feedparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Item:
    section: str
    title: str
    source: str
    url: str
    summary: str
    score: int = 0
    paragraph_md: str = ""


SOURCE_MAP: dict[str, str] = {
    "theguardian.com": "The Guardian",
    "bbci.co.uk": "BBC News",  # el feed vive en feeds.bbci.co.uk, no en bbc.co.uk
    "bbc.co.uk": "BBC News",
    "aljazeera.com": "Al Jazeera",
    "delfino.cr": "Delfino.cr",
    "semanariouniversidad.com": "Semanario Universidad",
    "arstechnica.com": "Ars Technica",
}

FEEDS: list[tuple[str, list[str]]] = [
    ("MUNDO", [
        "https://www.theguardian.com/world/rss",
        "https://www.theguardian.com/world/americas/rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ]),
    ("COSTA RICA", [
        "https://delfino.cr/feed",
        "https://semanariouniversidad.com/feed",
    ]),
    ("TECNOLOGÍA", [
        "https://www.theguardian.com/technology/rss",
        "https://feeds.arstechnica.com/arstechnica/index",
    ]),
]

MAX_PER_FEED = 6
MAX_AGE_HOURS = 48  # only fetch articles from the last 48 hours (UTC)
FEED_WORKERS = 8    # feeds are network-bound and independent; fetch them at once


def _source_name(url: str) -> str:
    for domain, name in SOURCE_MAP.items():
        if domain in url:
            return name
    return url.split("//")[1].split("/")[0]


def _parse_feed(section_name: str, url: str) -> list[Item]:
    """Every eligible entry of one feed, unbounded. MAX_PER_FEED is applied later,
    after cross-feed dedup, so the cap still counts items that actually survive."""
    feed = feedparser.parse(url)
    source = _source_name(url)
    items: list[Item] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        link = entry.get("link") or ""
        if not title and not summary:
            continue
        # Date filter: skip articles older than MAX_AGE_HOURS
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published:
            try:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
                if age_hours > MAX_AGE_HOURS:
                    continue
            except (TypeError, ValueError):
                pass  # if date parsing fails, include the article
        items.append(Item(
            section=section_name,
            title=title,
            source=source,
            url=link,
            summary=summary[:500],
        ))
    return items


def fetch_items() -> list[Item]:
    jobs = [(section_name, url) for section_name, urls in FEEDS for url in urls]
    parsed: dict[tuple[str, str], list[Item]] = {}

    with ThreadPoolExecutor(max_workers=FEED_WORKERS) as pool:
        futures = {pool.submit(_parse_feed, section, url): (section, url) for section, url in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                parsed[job] = future.result()
            except Exception as e:
                print(f"  ERROR [{type(e).__name__}]: {e} — {job[1][:60]}")
                parsed[job] = []

    # Merge in FEEDS order, not completion order: when two feeds carry the same
    # story the winner must stay the one listed first, regardless of which thread
    # finished first.
    items: list[Item] = []
    seen: set[str] = set()
    for job in jobs:
        count = 0
        for item in parsed.get(job, []):
            if count >= MAX_PER_FEED:
                break
            key = item.title or item.summary[:80]
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
            count += 1

    return items
