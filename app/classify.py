# from urllib.parse import urlparse


KNOWN_CDN_HINTS = (
  "cdn",
  "cloudflare",
  "akamai",
  "fastly",
  "jsdelivr",
  "unpkg",
)


KNOWN_ANALYTICS_HINTS = (
  "analytics",
  "gtag",
  "google-analytics",
  "matomo",
)


def classify_domain(domain: str, page_domain: str, config) -> str:
  if domain == page_domain or domain.endswith("." + page_domain):
    return "FIRST_PARTY"

  lowered = domain.lower()

  if any(hint in lowered for hint in KNOWN_CDN_HINTS):
    return "CDN"

  if any(hint in lowered for hint in KNOWN_ANALYTICS_HINTS):
    return "ANALYTICS"

  return "OTHER"
