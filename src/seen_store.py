import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    url        TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    title_key  TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    section    TEXT NOT NULL DEFAULT '',
    sent       INTEGER NOT NULL DEFAULT 0,
    sent_on    TEXT,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seen_source_title ON seen(source, title_key);
CREATE INDEX IF NOT EXISTS idx_seen_last_seen ON seen(last_seen);
"""


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        if scheme in ("http", "https"):
            scheme = "https"
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parts.path.lower().rstrip("/")
        return urlunsplit((scheme, netloc, path, "", ""))
    except ValueError:
        return url.strip().lower()


def _normalize_title(title: str) -> str:
    text = title.lower().translate(_ACCENTS)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


class SeenStore:
    """Persistent memory of articles already delivered, so the 48h RSS window
    cannot re-introduce a story sent on a previous day. Only articles that were
    actually sent (mark_sent) block future runs; items merely seen (note_seen)
    are recorded for audit but never block."""

    def __init__(self, db_path):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def is_blocked(self, url: str, title: str = "", source: str = "") -> bool:
        ukey = _normalize_url(url)
        if not ukey:
            return False
        sql = "SELECT 1 FROM seen WHERE sent = 1 AND url = ?"
        params = [ukey]
        tkey = _normalize_title(title)
        if tkey and source:
            sql += " OR (source = ? AND title_key = ?)"
            params += [source, tkey]
        sql += " LIMIT 1"
        cur = self._conn.execute(sql, params)
        return cur.fetchone() is not None

    def mark_sent(self, items, day: str) -> int:
        n = 0
        for it in items:
            ukey = _normalize_url(it.url)
            if not ukey:
                continue
            tkey = _normalize_title(it.title)
            self._conn.execute(
                """INSERT INTO seen
                       (url, title, title_key, source, section, sent, sent_on, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET
                       title = excluded.title,
                       title_key = excluded.title_key,
                       source = excluded.source,
                       section = excluded.section,
                       sent = 1,
                       sent_on = excluded.sent_on,
                       last_seen = excluded.last_seen""",
                (ukey, it.title, tkey, it.source, it.section, day, day, day),
            )
            n += 1
        self._conn.commit()
        return n

    def note_seen(self, items, day: str) -> int:
        n = 0
        for it in items:
            ukey = _normalize_url(it.url)
            if not ukey:
                continue
            tkey = _normalize_title(it.title)
            self._conn.execute(
                """INSERT INTO seen
                       (url, title, title_key, source, section, sent, sent_on, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET
                       title = excluded.title,
                       title_key = excluded.title_key,
                       source = excluded.source,
                       section = excluded.section,
                       last_seen = excluded.last_seen""",
                (ukey, it.title, tkey, it.source, it.section, day, day),
            )
            n += 1
        self._conn.commit()
        return n

    def prune(self, days: int = 30) -> int:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        cur = self._conn.execute("DELETE FROM seen WHERE last_seen < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
