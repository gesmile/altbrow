# altbrow/cache.py
#
#   build_cache()
#   get_or_build_cache()
#   lookup_domain()
#   lookup_ip()

import ipaddress
import logging
import sqlite3

from datetime import datetime, timezone
from pathlib import Path

from altbrow import __version__
from altbrow.utils import format_size
from .config import LOCATION_DEFAULT_TIER

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_categories (
  id              INTEGER PRIMARY KEY,
  provider        TEXT    NOT NULL,
  location        TEXT    NOT NULL,
  category        TEXT    NOT NULL,
  category_name   TEXT    NOT NULL DEFAULT '',
  tier            INTEGER NOT NULL DEFAULT 2,
  subdomain_match INTEGER NOT NULL DEFAULT 1,
  entry_type      TEXT    NOT NULL,
  UNIQUE(provider, category, category_name, entry_type)
);

CREATE TABLE IF NOT EXISTS entries (
  id                  INTEGER PRIMARY KEY,
  value               TEXT    NOT NULL,
  registrable_domain  TEXT,
  is_cidr             INTEGER NOT NULL DEFAULT 0,
  provider_cat_id     INTEGER NOT NULL REFERENCES provider_categories(id),
  UNIQUE(value, provider_cat_id)
);

CREATE INDEX IF NOT EXISTS idx_entries_value
  ON entries(value);

CREATE INDEX IF NOT EXISTS idx_entries_registrable
  ON entries(registrable_domain)
  WHERE registrable_domain IS NOT NULL;

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _get_registrable_domain(domain: str) -> str | None:
  """Extract registrable domain (e.g. 'example.com' from 'cdn.example.com').

  Args:
    domain: Fully qualified domain name.

  Returns:
    Registrable domain string, or None if not determinable.
  """
  try:
    import tldextract
    ext = tldextract.extract(domain)
    if ext.domain and ext.suffix:
      return f"{ext.domain}.{ext.suffix}".lower()
  except Exception:
    pass
  return None


def _is_cidr(value: str) -> bool:
  """Return True if value is an IP network in CIDR notation.

  Args:
    value: String to check.

  Returns:
    True if value is a valid CIDR block, False otherwise.
  """
  try:
    ipaddress.ip_network(value, strict=False)
    return "/" in value
  except ValueError:
    return False


def _load_local_source(path_str: str, config_path: Path, provider_type: str = "") -> list[str]:
  """Read entries from a local file or glob pattern.

  Supports plain domain/IP lists, hosts file format, URL-first TSV/CSV,
  and Netscape Bookmark HTML files. Format is detected per-file by suffix:
  ``.html`` files are parsed with _parse_bookmark_html(); all other files
  are parsed with parse_entries().
  Absolute paths (e.g. /etc/hosts) are used as-is.
  Glob patterns (e.g. ``./provider.d/*.txt``) expand to all matching files.

  Args:
    path_str: File path or glob pattern, absolute or relative to altbrow.toml.
    config_path: Path to altbrow.toml, used to resolve relative paths.
    provider_type: Passed through to parse_entries() for format detection.

  Returns:
    List of domain or IP strings.
  """
  from .fetch_remote import _parse_bookmark_html, parse_entries

  source_path = Path(path_str)
  if not source_path.is_absolute():
    source_path = config_path.parent / source_path

  matches = sorted(source_path.parent.glob(source_path.name))
  if not matches:
    logger.warning("Local source not found: %s", source_path)
    return []

  entries = []
  for match in matches:
    if match.suffix.lower() == ".html":
      entries.extend(_parse_bookmark_html(match))
    else:
      entries.extend(
        parse_entries(
          match.read_text(encoding="utf-8", errors="replace"),
          source_name=match.name,
          provider_type=provider_type,
        )
      )
  return entries


def build_cache(
  cache_path: Path,
  provider_config: dict,
  config_path: Path,
) -> None:
  """Build the SQLite cache from all enabled static providers.

  Reads inline, local, and remote providers from provider_config.
  DNS providers are skipped — they are queried live at runtime.

  Args:
    cache_path: Path where the SQLite DB will be created or replaced.
    provider_config: Parsed provider.toml dictionary.
    config_path: Path to altbrow.toml (used to resolve relative paths).
  """
  logger.info("Building cache: %s", cache_path)
  cache_path.parent.mkdir(parents=True, exist_ok=True)

  # always start fresh — partial updates make no sense when all sources are re-read
  if cache_path.exists():
    cache_path.unlink()
    logger.info("Removed existing cache: %s", cache_path)

  con = sqlite3.connect(cache_path)

  # performance pragmas — must be set before schema creation
  con.execute("PRAGMA page_size = 4096")
  con.execute("PRAGMA journal_mode = OFF")
  con.execute("PRAGMA synchronous = OFF")
  con.execute("PRAGMA temp_store = MEMORY")
  con.execute("PRAGMA cache_size = -64000")   # 64MB build cache

  con.executescript(SCHEMA)

  entry_rows: list[tuple] = []
  active_providers: list[str] = []

  # cache of (pname, location, category, cat_name, tier, subdomain_match, ptype) → pc_id
  pc_cache: dict[tuple, int] = {}

  def _get_pc_id(
    pname: str,
    location: str,
    category: str,
    cat_name: str | None,
    tier: int,
    subdomain_match: int,
    ptype: str,
  ) -> int:
    """Insert provider category if new, return its id.

    Args:
      pname: Provider name.
      location: Provider location (inline/local/remote/dns).
      category: altbrow mapping category.
      cat_name: Human-readable category name; None coerced to ''.
      tier: Integer tier for winner selection.
      subdomain_match: 1 if subdomain matching enabled, 0 otherwise.
      ptype: 'domain' or 'ip'.

    Returns:
      Integer id from provider_categories table.
    """
    cat_name_db = cat_name or ""
    key = (pname, location, category, cat_name_db, tier, subdomain_match, ptype)
    if key in pc_cache:
      return pc_cache[key]
    con.execute("""
      INSERT OR IGNORE INTO provider_categories
        (provider, location, category, category_name, tier, subdomain_match, entry_type)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (pname, location, category, cat_name_db, tier, subdomain_match, ptype))
    pc_id = con.execute("""
      SELECT id FROM provider_categories
      WHERE provider=? AND category=? AND category_name=? AND entry_type=?
    """, (pname, category, cat_name_db, ptype)).fetchone()[0]
    pc_cache[key] = pc_id
    return pc_id

  providers = provider_config.get("provider", {})

  for pname, p in providers.items():
    if not p.get("enabled", False):
      logger.debug("Provider '%s' disabled, skipping", pname)
      continue

    location = p.get("location")
    ptype = p.get("type")

    # DNS providers are live-only, not cached statically
    if location == "dns":
      logger.debug("Provider '%s' is dns, skipping for static cache", pname)
      continue

    # geoip providers are handled by extract_geodbs, not inserted into DB
    if ptype == "geoip":
      logger.debug("Provider '%s' is geoip, handled by extract_geodbs", pname)
      continue

    active_providers.append(pname)
    logger.info("Loading provider '%s' (%s/%s)", pname, location, ptype)
    subdomain_match = 1 if p.get("subdomain_match", True) else 0

    # remote providers: fetch_remote_provider handles all categories internally
    if location == "remote":
      from .fetch_remote import fetch_remote_provider
      for entry, ctx in fetch_remote_provider(pname, p):
        remote_tier = ctx.get("tier", LOCATION_DEFAULT_TIER["remote"])
        cat_name = ctx["name"]
        category = ctx["category"]
        eptype = ctx["ptype"]
        if eptype == "domain":
          pc_id = _get_pc_id(pname, "remote", category, cat_name, remote_tier, subdomain_match, "domain")
          reg = _get_registrable_domain(entry)
          entry_rows.append((entry, reg, 0, pc_id))
        elif eptype == "ip":
          pc_id = _get_pc_id(pname, "remote", category, cat_name, remote_tier, subdomain_match, "ip")
          cidr_flag = 1 if _is_cidr(entry) else 0
          entry_rows.append((entry, None, cidr_flag, pc_id))
      continue

    for cat in p.get("category", []):
      if not cat.get("enabled", True):
        continue

      cat_name = cat.get("name")
      mappings = cat.get("mapping", [])
      sources  = cat.get("source", [])
      tier     = cat.get("tier", LOCATION_DEFAULT_TIER.get(location, 2))

      cat_entries: list[str] = []

      if location == "local":
        if "geoip" in mappings:
          continue  # handled by extract_geodbs(), not inserted into DB
        for src in sources:
          cat_entries.extend(_load_local_source(src, config_path, provider_type=ptype))

      elif location == "inline":
        cat_entries = list(sources)

      for entry in cat_entries:
        entry = entry.strip().lower()
        if not entry:
          continue

        for category in mappings:
          if ptype == "domain":
            pc_id = _get_pc_id(pname, location, category, cat_name, tier, subdomain_match, "domain")
            reg = _get_registrable_domain(entry)
            entry_rows.append((entry, reg, 0, pc_id))

          elif ptype == "ip":
            pc_id = _get_pc_id(pname, location, category, cat_name, tier, subdomain_match, "ip")
            cidr_flag = 1 if _is_cidr(entry) else 0
            entry_rows.append((entry, None, cidr_flag, pc_id))

  con.executemany(
    """INSERT OR IGNORE INTO entries
       (value, registrable_domain, is_cidr, provider_cat_id)
       VALUES (?, ?, ?, ?)""",
    entry_rows,
  )

  now = datetime.now(timezone.utc).isoformat()
  con.execute(
    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
    ("built_at", now),
  )
  con.execute(
    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
    ("altbrow_version", __version__),
  )
  domain_count = len(set(row[0] for row in entry_rows if row[1] is not None))
  ip_count     = len(set(row[0] for row in entry_rows if row[1] is None))
  con.execute(
    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
    ("domain_count", str(domain_count)),
  )
  con.execute(
    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
    ("ip_count", str(ip_count)),
  )
  pv = str(provider_config.get("meta", {}).get("version", ""))
  if pv:
    con.execute(
      "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
      ("provider_config_version", pv),
    )

  con.commit()
  con.close()

  # VACUUM must run outside any transaction in a fresh connection
  con2 = sqlite3.connect(cache_path)
  con2.execute("VACUUM")
  con2.close()

  size_label = format_size(cache_path.stat().st_size)
  logger.info(
    "Cache built: %s (%s) — %d entries from %d providers (%s)",
    cache_path,
    size_label,
    len(entry_rows),
    len(active_providers),
    ", ".join(active_providers),
  )

def _ensure_schema(cache_path: Path) -> None:
  """Create DB tables if they do not exist yet.

  Safe to call on every startup — uses CREATE TABLE IF NOT EXISTS.

  Args:
    cache_path: Path to the SQLite cache file.
  """
  cache_path.parent.mkdir(parents=True, exist_ok=True)
  con = sqlite3.connect(cache_path)

  # performance pragmas — must be set before schema creation
  con.execute("PRAGMA page_size = 4096")
  con.execute("PRAGMA journal_mode = OFF")
  con.execute("PRAGMA synchronous = OFF")
  con.execute("PRAGMA temp_store = MEMORY")
  con.execute("PRAGMA cache_size = -64000")   # 64MB build cache

  con.executescript(SCHEMA)
  con.commit()
  con.close()


def get_or_build_cache(
  cache_path: Path,
  provider_config: dict | None,
  config_path: Path,
) -> Path:
  """Return cache path, initialising schema and building lazily if needed.

  Always ensures the DB schema exists. If provider_config is given and
  the DB has no entries yet, triggers a full build.

  Args:
    cache_path: Expected path of the SQLite cache file.
    provider_config: Parsed provider.toml dict, or None if disabled.
    config_path: Path to altbrow.toml.

  Returns:
    Path to the ready cache DB.
  """
  _ensure_schema(cache_path)

  if provider_config is None:
    return cache_path

  # check if DB is empty — build if so
  con = sqlite3.connect(cache_path)
  count = con.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
  con.close()

  if count == 0:
    logger.info("Cache empty, building...")
    build_cache(cache_path, provider_config, config_path)

  # staleness check — warn if cache is older than 7 days
  con = sqlite3.connect(cache_path)
  row = con.execute("SELECT value FROM meta WHERE key = 'built_at'").fetchone()
  con.close()

  if row:
    try:
      built_at = datetime.fromisoformat(row[0])
      age_days = (datetime.now(timezone.utc) - built_at).days
      if age_days >= 7:
        logger.warning(
          "Cache is %d days old — consider rebuilding with --build-cache", age_days
        )
    except Exception:
      pass

  return cache_path


def lookup_domain(
  domain: str,
  cache_path: Path,
  config: dict | None = None,
  resolved_ips: list[str] | None = None,
) -> list[dict]:
  """Look up a domain, merging static DB and live DNS provider results.

  Tries exact value match first, then registrable domain fallback via JOIN.
  If config is provided and contains dns providers, queries them live in parallel.

  Args:
    domain: Fully qualified domain name to look up.
    cache_path: Path to the SQLite cache file.
    config: Merged altbrow config dict for DNS provider lookup. Optional.
    resolved_ips: Optional list; if provided, the resolved IPv4 string is appended
      when resolve-domains succeeds. Lets callers capture the IP without a second
      socket call.

  Returns:
    List of category dicts with keys:
      category, provider, location, name, tier
    Empty list if no match.
  """
  domain = domain.lower()
  reg = _get_registrable_domain(domain)

  con = sqlite3.connect(cache_path)
  con.row_factory = sqlite3.Row

  rows = con.execute("""
    SELECT pc.category, pc.provider, pc.location,
           pc.category_name, pc.tier
    FROM entries e
    JOIN provider_categories pc ON pc.id = e.provider_cat_id
    WHERE pc.entry_type = 'domain'
      AND (e.value = ? OR (e.registrable_domain = ? AND pc.subdomain_match = 1))
  """, (domain, reg)).fetchall()

  con.close()

  seen: set[tuple] = set()
  results = []

  for r in rows:
    key = (r["category"], r["provider"], r["category_name"])
    if key not in seen:
      seen.add(key)
      results.append({
        "category": r["category"],
        "provider": r["provider"],
        "location": r["location"],
        "name":     r["category_name"],
        "tier":     r["tier"],
      })

  # DNS live lookup — gated by dns-resolve-filter when configured.
  # No filter: all domains are queried unconditionally.
  # Filter set: DNS only runs if at least one static cache hit passes the filter.
  # Clean domains (no static hit) with an active filter are skipped for performance.
  if config:
    from .dns_lookup import dns_provider_lookup, _should_query_category
    dns_filter = config.get("dns-resolve-filter", {})

    if not dns_filter:
      should_query_dns = True
    else:
      should_query_dns = any(
        _should_query_category({"mapping": [r["category"]], "tier": r["tier"]}, dns_filter)
        for r in results
      )

    if should_query_dns:
      logger.debug("DNS provider lookup for: %s", domain)
      dns_results = dns_provider_lookup(domain, config)
      if dns_results:
        existing = {(r["category"], r["provider"]) for r in results}
        for r in dns_results:
          if (r["category"], r["provider"]) not in existing:
            results.append(r)
    else:
      logger.debug("DNS lookup skipped for %s (dns-resolve-filter)", domain)

  # resolve-domains: resolve domain to IP and check against IP provider lists
  if config:
    resolve = config.get("resolve", {})
    from .config import RESOLVE_DEFAULTS
    if resolve.get("resolve-domains", RESOLVE_DEFAULTS["resolve-domains"]):
      import socket as _socket
      try:
        addr_infos = _socket.getaddrinfo(domain, None, _socket.AF_INET)
        if addr_infos:
          ip_str = addr_infos[0][4][0]
          if resolved_ips is not None:
            resolved_ips.append(ip_str)
          ip_results = lookup_ip(ip_str, cache_path)
          if ip_results:
            existing = {(r["category"], r["provider"]) for r in results}
            for r in ip_results:
              if (r["category"], r["provider"]) not in existing:
                r["resolved_from"] = domain
                results.append(r)
      except Exception as exc:
        logger.debug("resolve-domains failed for %s: %s", domain, exc)

  return results


def lookup_ip(ip_str: str, cache_path: Path) -> list[dict]:
  """Look up an IP address, matching exact IPs and CIDRs.

  Exact matches via SQL JOIN, CIDR matches resolved in Python via ipaddress stdlib.
  DNS results are not merged for IPs (DNS providers work on domain level).

  Args:
    ip_str: IP address string (IPv4 or IPv6).
    cache_path: Path to the SQLite cache file.

  Returns:
    List of category dicts with keys:
      category, provider, location, name, tier
    Empty list if no match or invalid IP.
  """
  try:
    ip = ipaddress.ip_address(ip_str)
  except ValueError:
    logger.warning("Invalid IP for lookup: %s", ip_str)
    return []

  con = sqlite3.connect(cache_path)
  con.row_factory = sqlite3.Row

  rows = con.execute("""
    SELECT pc.category, pc.provider, pc.location,
           pc.category_name, pc.tier
    FROM entries e
    JOIN provider_categories pc ON pc.id = e.provider_cat_id
    WHERE e.value = ? AND e.is_cidr = 0 AND pc.entry_type = 'ip'
  """, (ip_str,)).fetchall()

  results = [
    {
      "category": r["category"],
      "provider": r["provider"],
      "location": r["location"],
      "name":     r["category_name"],
      "tier":     r["tier"],
    }
    for r in rows
  ]

  cidr_rows = con.execute("""
    SELECT e.value, pc.category, pc.provider, pc.location,
           pc.category_name, pc.tier
    FROM entries e
    JOIN provider_categories pc ON pc.id = e.provider_cat_id
    WHERE e.is_cidr = 1 AND pc.entry_type = 'ip'
  """).fetchall()

  con.close()

  for row in cidr_rows:
    try:
      network = ipaddress.ip_network(row["value"], strict=False)
      if ip in network:
        results.append({
          "category": row["category"],
          "provider": row["provider"],
          "location": row["location"],
          "name":     row["category_name"],
          "tier":     row["tier"],
        })
    except ValueError:
      logger.warning("Invalid CIDR in cache: %s", row["value"])

  return results
