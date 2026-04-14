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
from .config import LOCATION_DEFAULT_TIER

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS domains (
  id                INTEGER PRIMARY KEY,
  value             TEXT    NOT NULL,
  registrable_domain TEXT,
  category          TEXT    NOT NULL,
  provider          TEXT    NOT NULL,
  provider_location TEXT    NOT NULL,
  category_name     TEXT,
  updated_at        TEXT    NOT NULL,
  subdomain_match   INTEGER NOT NULL DEFAULT 1,
  tier              INTEGER NOT NULL DEFAULT 2,
  UNIQUE(value, category, provider)
);

CREATE INDEX IF NOT EXISTS idx_domains_value
  ON domains(value);

CREATE INDEX IF NOT EXISTS idx_domains_registrable
  ON domains(registrable_domain);

CREATE TABLE IF NOT EXISTS ips (
  id                INTEGER PRIMARY KEY,
  value             TEXT    NOT NULL,
  is_cidr           INTEGER NOT NULL DEFAULT 0,
  category          TEXT    NOT NULL,
  provider          TEXT    NOT NULL,
  provider_location TEXT    NOT NULL,
  category_name     TEXT,
  tier              INTEGER NOT NULL DEFAULT 2,
  updated_at        TEXT    NOT NULL,
  UNIQUE(value, category, provider)
);

CREATE INDEX IF NOT EXISTS idx_ips_value
  ON ips(value);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _now() -> str:
  """Return current UTC time as ISO8601 string."""
  return datetime.now(timezone.utc).isoformat()


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


def _load_local_source(path_str: str, config_path: Path) -> list[str]:
  """Read entries from a local file in altbrow list or hosts format.

  Supports both plain domain/IP lists and hosts file format
  (``0.0.0.0 domain`` / ``127.0.0.1 domain`` lines) via parse_entries().
  Absolute paths (e.g. /etc/hosts) are used as-is.

  Args:
    path_str: File path as defined in provider source (absolute or relative
      to altbrow.toml).
    config_path: Path to altbrow.toml, used to resolve relative paths.

  Returns:
    List of domain or IP strings.
  """
  from .fetch_remote import parse_entries

  source_path = Path(path_str)
  if not source_path.is_absolute():
    source_path = config_path.parent / source_path

  if not source_path.exists():
    logger.warning("Local source not found: %s", source_path)
    return []

  return parse_entries(source_path.read_text(encoding="utf-8", errors="replace"))


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

  now = _now()
  domain_rows = []
  ip_rows = []
  active_providers = []

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
        if ctx["ptype"] == "domain":
          reg = _get_registrable_domain(entry)
          domain_rows.append((
            entry, reg, ctx["category"], pname,
            "remote", ctx["category_name"], remote_tier, now, subdomain_match,
          ))
        elif ctx["ptype"] == "ip":
          cidr_flag = 1 if _is_cidr(entry) else 0
          ip_rows.append((
            entry, cidr_flag, ctx["category"], pname,
            "remote", ctx["category_name"], remote_tier, now,
          ))
      continue

    for cat in p.get("category", []):
      if not cat.get("enabled", True):
        continue

      cat_name = cat.get("name")
      mappings = cat.get("mapping", [])
      sources  = cat.get("source", [])
      tier     = cat.get("tier", LOCATION_DEFAULT_TIER.get(location, 2))

      entries: list[str] = []

      if location == "local":
        for src in sources:
          entries.extend(_load_local_source(src, config_path))

      elif location == "inline":
        entries = list(sources)

      # Insert each entry × each mapping
      for entry in entries:
        entry = entry.strip().lower()
        if not entry:
          continue

        for category in mappings:

          if ptype == "domain":
            reg = _get_registrable_domain(entry)
            domain_rows.append((
              entry, reg, category, pname,
              location, cat_name, tier, now, subdomain_match,
            ))

          elif ptype == "ip":
            cidr_flag = 1 if _is_cidr(entry) else 0
            ip_rows.append((
              entry, cidr_flag, category, pname,
              location, cat_name, tier, now,
            ))

  con.executemany(
    """INSERT OR IGNORE INTO domains
       (value, registrable_domain, category, provider, provider_location, category_name, tier, updated_at, subdomain_match)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    domain_rows,
  )

  con.executemany(
    """INSERT OR IGNORE INTO ips
       (value, is_cidr, category, provider, provider_location, category_name, tier, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    ip_rows,
  )

  con.execute(
    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
    ("built_at", now),
  )
  con.execute(
    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
    ("altbrow_version", __version__),
  )

  con.commit()
  con.close()

  # VACUUM must run outside any transaction in a fresh connection
  con2 = sqlite3.connect(cache_path)
  con2.execute("VACUUM")
  con2.close()

  logger.info(
    "Cache built: %d domain entries, %d ip entries from %d providers (%s)",
    len(domain_rows),
    len(ip_rows),
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
  the DB has no domain entries yet, triggers a full build.

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
  count = con.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
  con.close()

  if count == 0:
    logger.info("Cache empty, building...")
    build_cache(cache_path, provider_config, config_path)

  return cache_path


def lookup_domain(
  domain: str,
  cache_path: Path,
  config: dict | None = None,
) -> list[dict]:
  """Look up a domain, merging static DB and live DNS provider results.

  Tries exact value match first, then registrable domain fallback.
  If config is provided and contains dns providers, queries them live in parallel.

  Args:
    domain: Fully qualified domain name to look up.
    cache_path: Path to the SQLite cache file.
    config: Merged altbrow config dict for DNS provider lookup. Optional.

  Returns:
    List of category dicts with keys:
      category, provider, provider_location, category_name, tier
    Empty list if no match.
  """
  domain = domain.lower()
  reg = _get_registrable_domain(domain)

  con = sqlite3.connect(cache_path)
  con.row_factory = sqlite3.Row

  # exact match — always
  rows_exact = con.execute(
    "SELECT * FROM domains WHERE value = ?",
    (domain,),
  ).fetchall()

  # registrable domain match — only for providers with subdomain_match = 1
  # always run, merged with exact results
  rows_reg = []
  if reg:
    rows_reg = con.execute(
      "SELECT * FROM domains WHERE registrable_domain = ? AND subdomain_match = 1",
      (reg,),
    ).fetchall()

  # merge: exact match + registrable match, skip rows already covered by exact
  exact_ids = {r["id"] for r in rows_exact}
  rows = list(rows_exact) + [r for r in rows_reg if r["id"] not in exact_ids]

  con.close()

  seen = set()
  results = []

  for r in rows:
    key = (r["category"], r["provider"], r["category_name"])
    if key not in seen:
      seen.add(key)
      results.append({
        "category":          r["category"],
        "provider":          r["provider"],
        "provider_location": r["provider_location"],
        "category_name":     r["category_name"],
        "tier":              r["tier"],
      })

  # DNS live lookup — all enabled DNS providers are always queried.
  # DNS providers (Pi-hole, OpenDNS) are independent classification sources.
  # dns-resolve-filter controls which provider categories are queried
  # inside dns_provider_lookup, not whether DNS runs at all.
  if config:
    from .dns_lookup import dns_provider_lookup
    logger.debug("DNS provider lookup for: %s", domain)
    dns_results = dns_provider_lookup(domain, config)
    if dns_results:
      existing = {(r["category"], r["provider"]) for r in results}
      for r in dns_results:
        if (r["category"], r["provider"]) not in existing:
          results.append(r)

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

  Exact matches via SQL, CIDR matches resolved in Python via ipaddress stdlib.
  DNS results are not merged for IPs (DNS providers work on domain level).

  Args:
    ip_str: IP address string (IPv4 or IPv6).
    cache_path: Path to the SQLite cache file.

  Returns:
    List of category dicts with keys:
      category, provider, provider_location, category_name
    Empty list if no match or invalid IP.
  """
  try:
    ip = ipaddress.ip_address(ip_str)
  except ValueError:
    logger.warning("Invalid IP for lookup: %s", ip_str)
    return []

  con = sqlite3.connect(cache_path)
  con.row_factory = sqlite3.Row

  rows = con.execute(
    "SELECT * FROM ips WHERE value = ? AND is_cidr = 0",
    (ip_str,),
  ).fetchall()

  results = [
    {
      "category":          r["category"],
      "provider":          r["provider"],
      "provider_location": r["provider_location"],
      "category_name":     r["category_name"],
      "tier":              r["tier"],
    }
    for r in rows
  ]

  cidr_rows = con.execute(
    "SELECT * FROM ips WHERE is_cidr = 1"
  ).fetchall()

  con.close()

  for row in cidr_rows:
    try:
      network = ipaddress.ip_network(row["value"], strict=False)
      if ip in network:
        results.append({
          "category":          row["category"],
          "provider":          row["provider"],
          "provider_location": row["provider_location"],
          "category_name":     row["category_name"],
          "tier":              row["tier"],
        })
    except ValueError:
      logger.warning("Invalid CIDR in cache: %s", row["value"])

  return results
