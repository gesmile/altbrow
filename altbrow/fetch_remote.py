# altbrow/fetch_remote.py
#
#   parse_entries()
#   parse_list()
#   fetch_remote_source()
#   fetch_remote_provider()

import logging
import re

import requests

from .config import LOCATION_DEFAULT_TIER

logger = logging.getLogger(__name__)

# Metadata key pattern: "# Key : Value" or "# key: value"
_META_RE = re.compile(
  r'^[ \t]{0,9}#[ \t]{0,2}([A-Za-z0-9][A-Za-z0-9._ -]{0,31})[ \t]{0,9}:[ \t]{0,5}(.{0,256})$'
)

_ALLOWED_META_KEYS = {
  "name", "list", "license", "source", "created",
  "updated", "version", "description", "total entries",
}

# hosts-format: line starts with an IP address token followed by whitespace
_HOSTS_LINE_RE = re.compile(r'^\s*([0-9a-fA-F.:]+)\s+(.+)')

# well-known non-domain tokens to skip from hosts files
_HOSTS_SKIP = {
  "localhost", "localhost.localdomain", "local",
  "broadcasthost", "ip6-localhost", "ip6-loopback", "ip6-localnet",
  "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters", "ip6-allhosts",
}


def _is_ip(token: str) -> bool:
  """Return True if token is a valid IPv4 or IPv6 address.

  Args:
    token: String to check.

  Returns:
    True if token parses as an IP address.
  """
  import ipaddress
  try:
    ipaddress.ip_address(token)
    return True
  except ValueError:
    return False


def parse_entries(text: str) -> list[str]:
  """Extract domain or IP entries from a list in altbrow or hosts format.

  Supports two formats transparently:

  - **altbrow list format**: one domain/IP per line, ``#`` comments ignored
  - **hosts file format**: ``<ip> hostname [hostname ...]`` lines —
    any IP address is accepted (not just 0.0.0.0/127.0.0.1), multiple
    hostnames per line are all extracted, inline ``#`` comments are stripped

  Format is detected per-line so mixed files work correctly.
  Leading comment blocks (metadata) are skipped like all other comments.

  Args:
    text: Raw text content of a list file or HTTP response.

  Returns:
    List of domain or IP strings, lowercased and stripped.
  """
  entries: list[str] = []

  for line in text.splitlines():
    stripped = line.strip()

    if not stripped or stripped.startswith("#"):
      continue

    m = _HOSTS_LINE_RE.match(stripped)
    if m and _is_ip(m.group(1)):
      # hosts format — extract all hostnames after the IP, strip inline comment
      rest = m.group(2)
      if "#" in rest:
        rest = rest[:rest.index("#")]
      for token in rest.split():
        token = token.lower()
        if token and token not in _HOSTS_SKIP:
          entries.append(token)
    else:
      # plain list format — one entry per line, strip inline comment
      entry = stripped
      if "#" in entry:
        entry = entry[:entry.index("#")].strip()
      if entry:
        entries.append(entry.lower())

  return entries


def parse_list(text: str) -> tuple[dict, list[str]]:
  """Parse a domain or IP list, extracting metadata and entries.

  Reads optional metadata from leading comment lines (``# key: value``),
  then delegates entry extraction to ``parse_entries()`` which handles
  both altbrow list format and hosts file format.

  Metadata is only read from leading comment lines before the first
  non-comment line — same convention as altbrow list format.

  Args:
    text: Raw text content of the list file or HTTP response.

  Returns:
    Tuple of:
      meta    - dict of parsed metadata keys (lowercased, spaces→underscore)
      entries - list of domain or IP strings from parse_entries()
  """
  meta: dict = {}
  header_done = False

  for line in text.splitlines():
    stripped = line.strip()
    if not stripped:
      continue
    if stripped.startswith("#"):
      if not header_done:
        m = _META_RE.match(stripped)
        if m:
          key = m.group(1).strip().lower().replace(" ", "_")
          val = m.group(2).strip()
          if key in _ALLOWED_META_KEYS or any(
            key == k.replace(" ", "_") for k in _ALLOWED_META_KEYS
          ):
            meta[key] = val
      continue
    header_done = True
    break  # stop at first non-comment line — entries handled by parse_entries

  return meta, parse_entries(text)


def fetch_remote_source(url: str, timeout: int = 15) -> tuple[dict, list[str]]:
  """Fetch a remote list URL and parse it.

  Args:
    url: HTTP or HTTPS URL of the list.
    timeout: Request timeout in seconds.

  Returns:
    Tuple of (meta, entries) from parse_list().

  Raises:
    requests.exceptions.RequestException: On network or HTTP errors.
  """
  logger.debug("Fetching remote source: %s", url)

  response = requests.get(url, timeout=timeout)
  response.raise_for_status()

  meta, entries = parse_list(response.text)

  logger.debug(
    "Fetched %s: %d entries, meta=%s",
    url, len(entries), meta
  )

  return meta, entries


def fetch_remote_provider(
  pname: str,
  p: dict,
) -> list[tuple[str, dict]]:
  """Fetch all enabled categories of a remote provider.

  Fetches each unique source URL only once, then distributes entries
  to all categories that reference the same URL.

  Args:
    pname: Provider name (for logging).
    p: Provider config dict from provider.toml.

  Returns:
    List of tuples: (entry, context) where context contains:
      category, provider, provider_location, category_name, meta
  """
  results = []
  ptype = p.get("type")

  # fetch each URL only once
  url_cache: dict[str, tuple[dict, list[str]]] = {}

  for cat in p.get("category", []):
    if not cat.get("enabled", True):
      continue

    cat_name = cat.get("name")
    mappings = cat.get("mapping", [])
    sources  = cat.get("source", [])
    tier     = cat.get("tier", LOCATION_DEFAULT_TIER["remote"])

    for url in sources:
      if url not in url_cache:
        try:
          url_cache[url] = fetch_remote_source(url)
          logger.info(
            "Provider '%s' fetched %d entries from %s",
            pname, len(url_cache[url][1]), url
          )
        except Exception as exc:
          logger.warning("Failed to fetch '%s' from %s: %s", pname, url, exc)
          url_cache[url] = ({}, [])

      meta, entries = url_cache[url]

      for entry in entries:
        entry = entry.strip().lower()
        if not entry:
          continue

        for category in mappings:
          results.append((entry, {
            "category":          category,
            "provider":          pname,
            "provider_location": "remote",
            "category_name":     cat_name,
            "tier":              tier,
            "meta":              meta,
            "ptype":             ptype,
          }))

  return results