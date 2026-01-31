from bs4 import BeautifulSoup
from urllib.parse import urlparse

from extruct import extract
from w3lib.html import get_base_url

from classify_domain import classify_domain
from classify_cookies import classify_cookies

import logging
logger = logging.getLogger(__name__)

def extract_data(fetch_result: dict, config) -> dict:
  html = fetch_result["html"]
  final_url = fetch_result["final_url"]
  headers = fetch_result["headers"]

  page_domain = urlparse(final_url).netloc
  base_url = get_base_url(html, final_url)
  soup = BeautifulSoup(html, "lxml")

  # ---------- Structured Data ----------
  structured = extract(
    html,
    base_url=base_url,
    syntaxes=["json-ld", "microdata"],
  )

  # ---------- External Domains ----------
  external_domains = set()

  for tag in soup.find_all(["a", "img", "script", "link", "iframe"]):
    url = tag.get("href") or tag.get("src")
    if not url:
      continue
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != page_domain:
      external_domains.add(parsed.netloc)

  classified_domains = [
    {
      "domain": d,
      "class": classify_domain(d, page_domain, config),
    }
    for d in sorted(external_domains)
  ]

  # ---------- Cookies ----------
  raw_cookies = headers.get("Set-Cookie")
  classified_cookies = []


  if raw_cookies:
    try:
      for raw in raw_cookies.split(","):
        classified_cookies.append(
          classify_cookies(raw.strip(), page_domain, config)
        )
    except Exception as exc:
      logger.warning("Cookie parsing failed: %s", exc)


  return {
    "structured_data": structured,
    "signals": {
      "external_domains": classified_domains,
      "cookies": classified_cookies,
    },
  }

def extract_cookies(cookiejar, page_domain: str) -> list[dict]:
  cookies = []

  for c in cookiejar:
    cookies.append({
      "name": c.name,
      "domain": c.domain.lstrip("."),
      "path": c.path,
      "secure": c.secure,
      "httponly": c.has_nonstandard_attr("HttpOnly"),
      "samesite": c.get_nonstandard_attr("SameSite"),
      "expires": c.expires,
      "class": classify_domain(
        c.domain.lstrip("."),
        page_domain,
        config
      ),
    })

  return cookies
