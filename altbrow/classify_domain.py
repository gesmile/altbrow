# altbrow/classify_domain.py
#
#   classify_domain()
#   classify_ip()

import logging

from pathlib import Path
from .domain_utils import get_registrable_domain
from .cache import lookup_domain, lookup_ip

logger = logging.getLogger(__name__)


def _relation(domain: str, page_domain: str) -> str:
  """Determine structural relation of domain to the analysed page.

  Rules (TARGET example: www.example.com, registrable: example.com):

    FIRST_PARTY — domain is exactly the TARGET host (www.example.com)
                  or exactly the registrable root (example.com)
    SUBDOMAIN   — domain is a strict child of the TARGET host
                  (m.example.com is child of www.example.com)
    PEER        — same registrable domain, but neither TARGET nor its child
                  (ai.example.com, images.example.com — lateral siblings)
    EXTERNAL    — different registrable domain

  Args:
    domain: The domain to classify.
    page_domain: The hostname of the analysed page (TARGET host).

  Returns:
    'FIRST_PARTY' | 'SUBDOMAIN' | 'PEER' | 'EXTERNAL'
  """
  domain      = domain.lower()
  page_domain = page_domain.lower()

  reg_domain = get_registrable_domain(domain)
  reg_page   = get_registrable_domain(page_domain)

  if reg_domain != reg_page:
    return "EXTERNAL"

  # same registrable domain — determine exact relation
  if domain == page_domain:
    return "FIRST_PARTY"

  if domain == reg_page:
    return "FIRST_PARTY"

  # strict child: domain ends with "." + page_domain
  if domain.endswith("." + page_domain):
    return "SUBDOMAIN"

  return "PEER"


def classify_domain(
  domain: str,
  page_domain: str,
  cache_path: Path,
) -> dict:
  """Classify an external domain against the provider cache.

  Determines the structural relation to the analysed page and looks up
  all matching provider categories from the SQLite cache, including any
  live DNS provider results.

  Args:
    domain: Fully qualified domain name to classify.
    page_domain: Hostname of the analysed page (used for relation).
    cache_path: Path to the SQLite cache file.

  Returns:
    Dict with keys:
      value             - normalised domain string
      registrable_domain - e.g. 'example.com'
      relation          - 'FIRST_PARTY' | 'SUBDOMAIN' | 'PEER' | 'EXTERNAL'
      categories        - list of dicts (category, provider,
                          provider_location, category_name)
                          empty list if no provider match
  """
  domain      = domain.lower()
  page_domain = page_domain.lower()

  reg_domain = get_registrable_domain(domain)
  relation   = _relation(domain, page_domain)

  categories = sorted(
    lookup_domain(domain, cache_path),
    key=lambda c: c.get("tier", 2),
  )

  return {
    "value":              domain,
    "registrable_domain": reg_domain,
    "relation":           relation,
    "categories":         categories,
  }


def classify_ip(
  ip_str: str,
  cache_path: Path,
) -> dict:
  """Classify an IP address against the provider cache.

  Matches exact IPs and CIDR blocks from the SQLite cache.

  Args:
    ip_str: IP address string (IPv4 or IPv6).
    cache_path: Path to the SQLite cache file.

  Returns:
    Dict with keys:
      value      - original IP string
      relation   - always 'EXTERNAL' (IPs are never first-party)
      categories - list of dicts (category, provider,
                   provider_location, category_name)
                   empty list if no match
  """
  categories = sorted(
    lookup_ip(ip_str, cache_path),
    key=lambda c: c.get("tier", 2),
  )

  return {
    "value":      ip_str,
    "relation":   "EXTERNAL",
    "categories": categories,
  }
