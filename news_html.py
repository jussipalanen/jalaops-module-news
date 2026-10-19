"""HTML for news content: an allowlist sanitizer and plain text.

The content is shown in the module's view with innerHTML, in a frame where
inline scripts may run, so everything that isn't on the allowlist is removed
before it's saved and again before it's shown: scripts, styles, event
handlers (on...), images and frames from other addresses, and links that
aren't http(s), mailto or tel.
"""

import html
import re
from html.parser import HTMLParser

# Tags that are kept, with the attributes each may have.
ALLOWED_TAGS = {
    "a": {"href", "title"},
    "b": set(),
    "blockquote": set(),
    "br": set(),
    "code": set(),
    "div": set(),
    "em": set(),
    "h2": set(),
    "h3": set(),
    "h4": set(),
    "hr": set(),
    "i": set(),
    "li": set(),
    "mark": set(),
    "ol": set(),
    "p": set(),
    "pre": set(),
    "s": set(),
    "small": set(),
    "span": set(),
    "strong": set(),
    "sub": set(),
    "sup": set(),
    "table": set(),
    "tbody": set(),
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "thead": set(),
    "tr": set(),
    "u": set(),
    "ul": set(),
}

# Tags without an end tag.
VOID_TAGS = {"br", "hr"}

# A news item's title is its only h1, so headings in the content start from h2.
RENAMED_TAGS = {"h1": "h2", "h5": "h4", "h6": "h4"}

# Tags removed together with everything inside them.
DROPPED_WITH_CONTENT = {
    "script", "style", "iframe", "object", "embed", "template", "noscript",
    "svg", "math", "textarea", "select", "title", "head", "frameset", "frame",
}

SAFE_URL = re.compile(r"^(https?:|mailto:|tel:)", re.IGNORECASE)


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.open_tags = []
        self.skipping = []

    def handle_starttag(self, tag, attrs):
        tag = RENAMED_TAGS.get(tag, tag)

        if tag in DROPPED_WITH_CONTENT:
            self.skipping.append(tag)
            return

        if self.skipping or tag not in ALLOWED_TAGS:
            return

        kept = []
        for name, value in attrs:
            if name not in ALLOWED_TAGS[tag] or value is None:
                continue
            if name == "href":
                value = value.strip()
                # Browsers skip whitespace and control characters inside a
                # scheme ("java\tscript:"), so the scheme is checked without them.
                if not SAFE_URL.match(re.sub(r"[\x00-\x20]", "", value)):
                    continue
            if name in {"colspan", "rowspan"} and not (value.isdigit() and 0 < int(value) <= 50):
                continue
            kept.append(f' {name}="{html.escape(value, quote=True)}"')

        if tag == "a":
            kept.append(' target="_blank" rel="noopener noreferrer"')

        self.parts.append(f"<{tag}{''.join(kept)}>")

        if tag not in VOID_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

        if RENAMED_TAGS.get(tag, tag) in DROPPED_WITH_CONTENT:
            self.skipping.pop()

    def handle_endtag(self, tag):
        tag = RENAMED_TAGS.get(tag, tag)

        if self.skipping:
            if tag == self.skipping[-1]:
                self.skipping.pop()
            return

        if tag not in self.open_tags:
            return

        # Closes the tags opened after this one too, so the result stays nested.
        while self.open_tags:
            open_tag = self.open_tags.pop()
            self.parts.append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(html.escape(data, quote=False))

    def result(self):
        self.close()
        return "".join(self.parts) + "".join(f"</{tag}>" for tag in reversed(self.open_tags))


HAS_TAGS = re.compile(r"<[a-zA-Z/!]")

# Tags that make their own blocks: with any of these, the content's layout is
# left to its HTML.
HAS_BLOCKS = re.compile(r"<(p|div|h[1-6]|ul|ol|li|table|blockquote|pre|hr)\b", re.IGNORECASE)


def paragraphs(content):
    """Text as paragraphs: a blank line starts a new one, and a line break
    stays a line break. Text without tags is escaped first; text with only
    inline tags (<strong>, <a>…) keeps them; HTML with blocks is left as it is."""
    if HAS_BLOCKS.search(content):
        return content
    if not HAS_TAGS.search(content):
        content = html.escape(content, quote=False)
    parts = [part.strip() for part in re.split(r"\n\s*\n", content.strip()) if part.strip()]
    return "".join(f"<p>{part.replace(chr(10), '<br>')}</p>" for part in parts)


def sanitize(content):
    """The content with only the allowed tags and attributes."""
    sanitizer = _Sanitizer()
    sanitizer.feed(content)
    return sanitizer.result()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROPPED_WITH_CONTENT:
            self.skipping += 1
        elif tag in {"br", "p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in DROPPED_WITH_CONTENT and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def plain_text(content):
    """The content's text without tags, on one line."""
    parser = _Text()
    parser.feed(content)
    parser.close()
    return " ".join("".join(parser.parts).split())
