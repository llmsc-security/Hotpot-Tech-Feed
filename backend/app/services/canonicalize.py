"""URL canonicalization — first stage of dedup.

Strips tracking params, lowercases the host, removes the fragment, drops
trailing slashes, and resolves a few common host aliases.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Tracking parameters that never change the underlying content.
_TRACKING_PREFIXES = ("utm_", "mc_", "hsa_", "fbclid", "gclid", "yclid", "_hs", "ref")
_TRACKING_EXACT = {
    "ref_src",
    "ref_url",
    "from",
    "share",
    "share_id",
    "spm",
    "feature",
}

_HOST_ALIASES = {
    "www.arxiv.org": "arxiv.org",
    "m.arxiv.org": "arxiv.org",
    "export.arxiv.org": "arxiv.org",
    "www.youtube.com": "youtube.com",
    "m.youtube.com": "youtube.com",
}


def canonicalize_url(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url.strip())

    scheme = parts.scheme.lower() or "https"
    if scheme == "http":
        scheme = "https"

    host = (parts.hostname or "").lower()
    host = _HOST_ALIASES.get(host, host)

    netloc = host
    if parts.port and not _is_default_port(scheme, parts.port):
        netloc = f"{host}:{parts.port}"

    # Filter query params
    kept = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        kl = k.lower()
        if any(kl.startswith(p) for p in _TRACKING_PREFIXES):
            continue
        if kl in _TRACKING_EXACT:
            continue
        kept.append((k, v))
    kept.sort()
    query = urlencode(kept, doseq=True)

    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Special case: arxiv abs/<id> sometimes carries a version suffix; the
    # versionless form is usually canonical.
    if host == "arxiv.org" and path.startswith("/abs/"):
        ident = path[len("/abs/"):]
        if "v" in ident:
            base = ident.split("v", 1)[0]
            if base:
                path = f"/abs/{base}"

    return urlunsplit((scheme, netloc, path, query, ""))


def _is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
