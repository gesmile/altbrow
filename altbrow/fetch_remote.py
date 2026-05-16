# altbrow/fetch_remote.py
#
#   _url_to_host()
#   _parse_bookmark_html()
#   _detect_delimiter()
#   parse_entries()
#   parse_list()
#   fetch_remote_source()
#   fetch_remote_provider()

import ipaddress
import logging
from pathlib import Path

import requests

from .config import ALLOWED_PROTOCOLS, LOCATION_DEFAULT_TIER

logger = logging.getLogger(__name__)

# Column delimiters checked in order — first match wins
_DELIMITERS = ("\t", " ", ";", ",")
_DELIMITER_DISPLAY = {"\t": "TAB", " ": "SPACE"}


def _url_to_host(url: str) -> str | None:
  """Extract hostname from an HTTP/HTTPS URL.

  Returns None for non-HTTP schemes (javascript:, mailto:, ftp:, …)
  or malformed URLs.

  Args:
    url: URL string.

  Returns:
    Lowercase hostname string, or None.
  """
  from urllib.parse import urlparse
  if not url.startswith(("http://", "https://")):
    return None
  return urlparse(url).hostname or None


def _parse_bookmark_html(path: Path) -> list[str]:
  """Parse a Netscape Bookmark HTML file and return all hostnames/IPs.

  Compatible with Firefox, Chrome, Edge, Safari bookmark exports.
  Uses _url_to_host() for consistent URL→hostname extraction.

  Args:
    path: Path to the bookmark HTML file.

  Returns:
    Deduplicated list of hostnames and IPs found in href attributes.
  """
  from bs4 import BeautifulSoup

  try:
    html = path.read_text(encoding="utf-8", errors="replace")
  except Exception as exc:
    logger.warning("Failed to read bookmark file %s: %s", path, exc)
    return []

  soup = BeautifulSoup(html, "lxml")
  seen: set[str] = set()
  hosts: list[str] = []

  for tag in soup.find_all("a", href=True):
    host = _url_to_host(tag["href"].strip())
    if host and host not in seen:
      seen.add(host)
      hosts.append(host)

  logger.info("Bookmark file %s: %d unique hosts", path.name, len(hosts))
  return hosts


def _is_ip(s: str) -> bool:
  """Return True if s is a valid IP address (IPv4 or IPv6, not CIDR)."""
  try:
    ipaddress.ip_address(s)
    return True
  except ValueError:
    return False


def _detect_delimiter(line: str) -> str:
  """Detect column delimiter from a representative data line.

  Checks delimiters in priority order: tab, space, semicolon, comma.
  Returns the first delimiter found in the line, or tab as fallback.

  Args:
    line: First non-comment data line of the source file.

  Returns:
    Single delimiter character.
  """
  for delim in _DELIMITERS:
    if delim in line:
      return delim
  return "\t"


def parse_entries(text: str, source_name: str = "", provider_type: str = "") -> list[str]:
  """Parse a line-based source into a list of domains, IPs, or CIDRs.

  Handles:
    - Plain domain/IP/CIDR lists (one entry per line)
    - Hosts file format: <IP> <hostname> — detected once from first data line
      when provider_type=="domain" and first column is a valid IP address.
      All standard sinkhole IPs are recognised (0.0.0.0, 127.0.0.1, ::, ::1, …).
    - URL-first TSV/CSV: https://example.com<TAB>Title<TAB>...
    - Quoted fields: "example.com","title" or 'example.com'
    - Any delimiter from _DELIMITERS (auto-detected from first data line)
    - Protocols matched case-insensitively via ALLOWED_PROTOCOLS
    - ABP filter format: ||domain^ or ||domain. (auto-detected)

  Comments (#, !, [Section]) and blank lines are ignored.
  Deduplication: per parse_entries() call (per source file).
  Cross-source deduplication is handled by SQLite UNIQUE constraint.

  Args:
    text: Raw file content as string.
    source_name: Optional filename for debug logging.
    provider_type: "domain" or "ip" — enables hosts-format detection when "domain".

  Returns:
    Deduplicated list of hostnames, IPs, or CIDRs.
  """
  from urllib.parse import urlparse

  lines = [
    ln for ln in text.splitlines()
    if ln.strip() and not ln.strip().startswith(("#", "!", "["))
  ]

  if not lines:
    return []

  is_abp = lines[0].strip().startswith("||")
  is_hosts = False

  if not is_abp:
    delimiter = _detect_delimiter(lines[0])
    if provider_type == "domain":
      first_col = lines[0].strip().split(delimiter, 1)[0].strip().strip("\"'")
      is_hosts = _is_ip(first_col)

  if source_name:
    if is_abp:
      logger.info("Source '%s': ABP filter format", source_name)
    elif is_hosts:
      delim_label = _DELIMITER_DISPLAY.get(delimiter, repr(delimiter))
      logger.info("Source '%s': hosts file format (delimiter %s)", source_name, delim_label)
    else:
      delim_label = _DELIMITER_DISPLAY.get(delimiter, repr(delimiter))
      logger.info("Source '%s': detected delimiter %s", source_name, delim_label)

  seen:    set[str]  = set()
  results: list[str] = []
  skipped: int       = 0

  if is_abp:
    for line in lines:
      line = line.strip()
      if not line.startswith("||"):
        skipped += 1
        continue
      entry = line[2:]
      if "^" in entry:
        entry = entry[: entry.index("^")]
      elif entry.endswith("."):
        entry = entry[:-1]
      else:
        skipped += 1
        continue
      if not entry or "/" in entry or "." not in entry:
        skipped += 1
        continue
      entry = entry.lower()
      if entry not in seen:
        seen.add(entry)
        results.append(entry)
  else:
    for line in lines:
      line = line.strip()
      if not line:
        skipped += 1
        continue

      if is_hosts:
        # hosts lines use arbitrary whitespace and may have multiple hostnames per line;
        # delimiter-based split handles neither — use split() on the comment-stripped line
        tokens = line.split("#")[0].split()
        if len(tokens) < 2:
          skipped += 1
          continue
        for domain in tokens[1:]:
          domain = domain.lower()
          if domain and domain not in seen:
            seen.add(domain)
            results.append(domain)
        continue

      parts = line.split(delimiter, 2)
      first = parts[0].strip().strip("\"'")

      if first.lower().startswith(tuple(ALLOWED_PROTOCOLS)):
        host = urlparse(first).hostname
        if not host:
          skipped += 1
          continue
        entry = host
      else:
        entry = first.split("#")[0].strip()

      entry = entry.lower()
      if not entry:
        skipped += 1
        continue

      if entry not in seen:
        seen.add(entry)
        results.append(entry)

  if source_name:
    if skipped:
      logger.info("Source '%s': skipped %d lines", source_name, skipped)
    logger.debug("Source '%s': %d unique entries parsed", source_name, len(results))

  return results


def parse_list(text: str, source_name: str = "", provider_type: str = "") -> list[str]:
  """Parse a domain or IP list and return entries.

  Delegates to ``parse_entries()`` which handles both altbrow list format
  and hosts file format.

  Args:
    text: Raw text content of the list file or HTTP response.
    source_name: Optional source identifier for debug logging.
    provider_type: Passed through to parse_entries() for format detection.

  Returns:
    List of domain or IP strings from parse_entries().
  """
  return parse_entries(text, source_name=source_name, provider_type=provider_type)


def fetch_remote_source(url: str, timeout: int = 15, provider_type: str = "") -> list[str]:
  """Fetch a remote list URL and parse it.

  Args:
    url: HTTP or HTTPS URL of the list.
    timeout: Request timeout in seconds.
    provider_type: Passed through to parse_list() for format detection.

  Returns:
    List of domain or IP strings from parse_list().

  Raises:
    requests.exceptions.RequestException: On network or HTTP errors.
  """
  logger.debug("Fetching remote source: %s", url)

  response = requests.get(url, timeout=timeout)
  response.raise_for_status()

  entries = parse_list(response.text, source_name=url, provider_type=provider_type)

  logger.debug("Fetched %s: %d entries", url, len(entries))

  return entries


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
      category, provider, location, name
  """
  results = []
  ptype = p.get("type")

  # fetch each URL only once
  url_cache: dict[str, list[str]] = {}

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
          url_cache[url] = fetch_remote_source(url, provider_type=ptype or "")
          logger.info(
            "Provider '%s' fetched %d entries from %s",
            pname, len(url_cache[url]), url
          )
        except Exception as exc:
          logger.warning("Failed to fetch '%s' from %s: %s", pname, url, exc)
          url_cache[url] = []

      for entry in url_cache[url]:
        entry = entry.strip().lower()
        if not entry:
          continue

        for category in mappings:
          results.append((entry, {
            "category": category,
            "provider": pname,
            "location": "remote",
            "name":     cat_name,
            "tier":     tier,
            "ptype":    ptype,
          }))

  return results