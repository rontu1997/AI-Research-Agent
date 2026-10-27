"""Plain-text escaping and link safety for anything third-party that reaches Markdown (DR-9)."""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_SPECIALS = "\`*_[]()<>#|~&!"


def escape_md(text: str) -> str:
    """Plain-text escape: no HTML, links, emphasis, tables or headings can be formed."""
    cleaned = _CONTROL_RE.sub(" ", text).strip()
    return "".join(f"\{ch}" if ch in _SPECIALS else ch for ch in cleaned)


def safe_url(url: str) -> str | None:
    """A percent-encoded http(s) URL, or None for any other scheme."""
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return quote(url.strip(), safe=":/?#[]@!$&'*+,;=%-._~")
