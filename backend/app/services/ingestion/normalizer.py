"""Lossless source storage with conservative, readable projections."""
from datetime import datetime
from html import unescape
from html.parser import HTMLParser


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def description_text(content: str | None) -> str | None:
    if content is None:
        return None
    parser = _TextParser()
    # Greenhouse content can contain entity-encoded HTML. Preserve original elsewhere.
    parser.feed(unescape(content))
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip()) or None


def source_date(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
