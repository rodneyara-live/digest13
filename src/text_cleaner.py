import re

from num2words import numbers_to_words


_CURRENCY_RE = re.compile(
    r"[₡¢]\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?(\s+colones)?",
    re.IGNORECASE,
)


def _fix_currency(text: str) -> str:
    def _repl(match: re.Match) -> str:
        integer = match.group(1).replace(".", "")
        decimal = match.group(2) or ""
        trailing = match.group(3) or ""
        num = f"{integer},{decimal}" if decimal else integer
        if trailing:
            return f"{num}{trailing}"
        return f"{num} colones"
    return _CURRENCY_RE.sub(_repl, text)


def strip_markdown(text: str) -> str:
    text = _fix_currency(text)
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"!\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^_{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = numbers_to_words(text)
    return text.strip()
