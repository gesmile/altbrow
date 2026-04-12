# altbrow/extract.py
#
#   extract_data()
#   extract_cookies()

import logging
import ipaddress

from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse

from extruct import extract
from w3lib.html import get_base_url

from .classify_domain import classify_domain, classify_ip
from .classify_cookies import classify_cookies

logger = logging.getLogger(__name__)

# HTML tags that reference external resources
_ASSET_TAGS = {
  "img":    "src",
  "script": "src",
  "link":   "href",
  "iframe": "src",
}
_LINK_TAGS = {
  "a": "href",
}


def _is_ip_address(host: str) -> bool:
  """Return True if host is a bare IP address (v4 or v6), not a hostname.

  Args:
    host: netloc value from urlparse, may include port (e.g. '10.0.0.1:8080').

  Returns:
    True if host resolves to an IP address.
  """
  # strip optional port
  host = host.rsplit(":", 1)[0].strip("[]")
  try:
    ipaddress.ip_address(host)
    return True
  except ValueError:
    return False


def extract_data(fetch_result: dict, cache_path: Path) -> dict:
  """Extract and classify structured data, external domains and cookies.

  Collects all external domain references from HTML tags, classifies each
  against the provider cache, and extracts structured data (JSON-LD,
  Microdata).

  When the target URL itself is a bare IP address, that IP is added to
  external_ips using classify_ip() so RFC1918 and other provider matches
  are visible in the output even when no HTML links were found.

  Args:
    fetch_result: Dict returned by fetch_url(), containing html, final_url,
      headers, cookies.
    cache_path: Path to the SQLite provider cache file.

  Returns:
    Dict with keys:
      structured_data - JSON-LD and Microdata blocks
      signals         - external_domains, external_ips, cookies
  """
  html      = fetch_result["html"]
  final_url = fetch_result["final_url"]
  headers   = fetch_result["headers"]

  page_host   = urlparse(final_url).netloc
  page_domain = page_host.rsplit(":", 1)[0].strip("[]")   # strip port / brackets
  base_url    = get_base_url(html, final_url)
  soup        = BeautifulSoup(html, "lxml")

  # ---------- Structured Data ----------
  structured = extract(
    html,
    base_url=base_url,
    syntaxes=["json-ld", "microdata"],
  )

  # ---------- Classify target host ----------
  classified_ips: list[dict] = []

  if _is_ip_address(page_domain):
    ip_result = classify_ip(page_domain, cache_path)
    ip_result["occurrence"] = "TARGET"
    classified_ips.append(ip_result)

  # TARGET domain entry — only for real hostnames, not bare IPs
  # (IPs are already handled in classified_ips above)
  target_result = None
  if not _is_ip_address(page_domain):
    target_result = classify_domain(page_domain, page_domain, cache_path)
    target_result["occurrence"] = "TARGET"

  # ---------- External Domains ----------
  # track occurrence per domain: asset | link | mixed
  # TODO: SELF_REF — domains found only in JSON-LD @id / Microdata itemid,
  #       not present in any HTML tag. Requires post-extraction diffing of
  #       structured_data domains against domain_occurrence. See OCCURRENCE.md.
  # TODO: COOKIE — domains found only in Set-Cookie Domain= attribute,
  #       not present in any HTML tag. Requires classify_cookies() integration
  #       into the domain signal pipeline. See OCCURRENCE.md.
  domain_occurrence: dict[str, set] = {}

  for tag in soup.find_all(list(_ASSET_TAGS) + list(_LINK_TAGS)):
    attr = _ASSET_TAGS.get(tag.name) or _LINK_TAGS.get(tag.name)
    url  = tag.get(attr)
    if not url:
      continue

    parsed = urlparse(url)
    if not parsed.netloc or parsed.netloc == page_host:
      continue

    kind = "asset" if tag.name in _ASSET_TAGS else "link"
    domain_occurrence.setdefault(parsed.netloc, set()).add(kind)

  classified_domains = [target_result] if target_result else []

  for domain, kinds in sorted(domain_occurrence.items()):
    if "asset" in kinds and "link" in kinds:
      occurrence = "MIXED"
    elif "asset" in kinds:
      occurrence = "ASSET"
    else:
      occurrence = "LINK_ONLY"

    result = classify_domain(domain, page_domain, cache_path)
    result["occurrence"] = occurrence
    classified_domains.append(result)

  # ---------- Cookies ----------
  raw_cookies        = headers.get("Set-Cookie")
  classified_cookies = []

  if raw_cookies:
    try:
      for raw in raw_cookies.split(","):
        classified_cookies.append(
          classify_cookies(raw.strip(), page_domain)
        )
    except Exception as exc:
      logger.warning("Cookie parsing failed: %s", exc)

  return {
    "structured_data": structured,
    "signals": {
      "external_domains": classified_domains,
      "external_ips":     classified_ips,
      "cookies":          classified_cookies,
    },
  }


def extract_cookies(cookiejar, page_domain: str, cache_path: Path) -> list[dict]:
  """Classify cookies from a requests CookieJar.

  Args:
    cookiejar: requests.cookies.RequestsCookieJar from fetch_url().
    page_domain: Hostname of the analysed page.
    cache_path: Path to the SQLite provider cache file.

  Returns:
    List of dicts with cookie attributes and domain classification.
  """
  cookies = []

  for c in cookiejar:
    domain = c.domain.lstrip(".")
    cookies.append({
      "name":      c.name,
      "domain":    domain,
      "path":      c.path,
      "secure":    c.secure,
      "httponly":  c.has_nonstandard_attr("HttpOnly"),
      "samesite":  c.get_nonstandard_attr("SameSite"),
      "expires":   c.expires,
      "class":     classify_domain(domain, page_domain, cache_path),
    })

  return cookies
