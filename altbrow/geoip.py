# altbrow/geoip.py
#
#   open_geodbs()
#   lookup_ip()
#   lookup_domain()
#   GeoReaders  (namedtuple)

import logging
import socket
import tarfile

from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class GeoReaders(NamedTuple):
  """Holds open MaxMind MMDB reader handles for the session.

  All fields may be None if the respective DB file is not found.
  City is used if present, Country as fallback.
  """
  country: object | None   # maxminddb.Reader or None
  asn:     object | None   # maxminddb.Reader or None
  city:    object | None   # maxminddb.Reader or None (superset of country)


def _extract_mmdb(tar_path: Path, dest_dir: Path) -> Path | None:
  """Extract .mmdb file from a MaxMind .tar.gz archive.

  Args:
    tar_path: Path to the .tar.gz file.
    dest_dir: Directory to extract the .mmdb file into.

  Returns:
    Path to the extracted .mmdb file, or None on failure.
  """
  try:
    with tarfile.open(tar_path, "r:gz") as tar:
      for member in tar.getmembers():
        if member.name.endswith(".mmdb"):
          member.name = Path(member.name).name  # strip directory prefix
          tar.extract(member, path=dest_dir)
          extracted = dest_dir / member.name
          logger.info("Extracted %s from %s", extracted.name, tar_path.name)
          return extracted
  except Exception as exc:
    logger.warning("Failed to extract %s: %s", tar_path.name, exc)
  return None


def extract_geodbs(config_path: Path, provider_cfg: dict | None = None) -> None:
  """Extract GeoLite2 .tar.gz files defined in geoip provider categories.

  Called during --build-cache. Existing .mmdb files are overwritten when
  a newer .tar.gz is found (determined by mtime). Garbage collection of
  old .tar.gz files is left to the user/admin.

  Args:
    config_path: Path to the active altbrow.toml file.
    provider_cfg: Full provider config dict (with sources). If None,
      falls back to scanning config dir for GeoLite2-*.tar.gz.
  """

  base = config_path.parent

  # collect (source_path, dest_dir) pairs from provider config
  tar_paths: list[Path] = []

  if provider_cfg:
    for pname, p in provider_cfg.get("provider", {}).items():
      if not p.get("enabled", False):
        continue
      location = p.get("location")
      for cat in p.get("category", []):
        if not cat.get("enabled", True):
          continue
        if "geoip" not in cat.get("mapping", []):
          continue
        for src in cat.get("source", []):
          if location == "local":
            src_path = Path(src)
            if not src_path.is_absolute():
              src_path = base / src
            # resolve glob pattern
            parent = src_path.parent
            pattern = src_path.name
            matches = sorted(parent.glob(pattern))
            if matches:
              tar_paths.append(matches[-1])  # newest by name
            else:
              logger.warning("GeoIP: no file matching %s", src)
          elif location == "remote":
            # download .tar.gz to config dir
            try:
              import requests as _req
              fname = src.rstrip("/").split("/")[-1]
              dest = base / fname
              logger.info("GeoIP: downloading %s", src)
              r = _req.get(src, timeout=30)
              r.raise_for_status()
              dest.write_bytes(r.content)
              tar_paths.append(dest)
            except Exception as exc:
              logger.warning("GeoIP: failed to download %s: %s", src, exc)
  else:
    # fallback: scan config dir
    tar_paths = sorted(base.glob("GeoLite2-*.tar.gz"))

  for tar_path in tar_paths:
    stem = tar_path.name.split("_")[0]  # GeoLite2-Country
    if not stem.startswith("GeoLite2-"):
      # try to get stem from mmdb inside archive
      stem = None
    mmdb_path = base / f"{stem}.mmdb" if stem else None
    # overwrite if tar is newer than existing mmdb
    if mmdb_path and mmdb_path.exists():
      if tar_path.stat().st_mtime <= mmdb_path.stat().st_mtime:
        logger.info("GeoIP: %s up to date, skipping", mmdb_path.name)
        continue
    _extract_mmdb(tar_path, base)


def open_geodbs(config_path: Path, allowed_names: set[str] | None = None) -> GeoReaders | None:
  """Open GeoLite2 MMDB readers from the directory of altbrow.toml.

  Looks for GeoLite2-Country.mmdb and GeoLite2-ASN.mmdb next to altbrow.toml.
  Missing files are logged as warnings, not errors — altbrow continues without GeoIP.

  Args:
    config_path: Path to the active altbrow.toml file.
    allowed_names: Set of DB names to open e.g. {"Country", "ASN", "City"}.
      If None, all found DBs are opened.

  Returns:
    GeoReaders namedtuple with open readers, or None if maxminddb is not installed.
  """
  try:
    import maxminddb
  except ImportError:
    logger.warning(
      "maxminddb not installed — GeoIP disabled. "
      "Install with: pip install maxminddb"
    )
    return None

  base = config_path.parent

  def _open(name: str, db_type: str) -> object | None:
    if allowed_names is not None and db_type not in allowed_names:
      logger.debug("GeoIP: %s disabled by provider config", db_type)
      return None
    path = base / name
    if not path.exists():
      logger.info("GeoIP: %s not found — lookup disabled", name)
      return None
    try:
      reader = maxminddb.open_database(str(path))
      logger.debug("GeoIP DB opened: %s", name)
      return reader
    except Exception as exc:
      logger.warning("Failed to open %s: %s", name, exc)
      return None

  city_reader    = _open("GeoLite2-City.mmdb",    "City")
  country_reader = _open("GeoLite2-Country.mmdb", "Country")
  asn_reader     = _open("GeoLite2-ASN.mmdb",     "ASN")

  if city_reader is None and country_reader is None and asn_reader is None:
    return None

  active = [n for n, r in [("City", city_reader), ("Country", country_reader), ("ASN", asn_reader)] if r]
  logger.debug("GeoIP ready: %s", ", ".join(active))

  return GeoReaders(country=country_reader, asn=asn_reader, city=city_reader)


def lookup_ip(ip_str: str, readers: GeoReaders) -> dict:
  """Look up GeoIP data for an IP address.

  Args:
    ip_str: IPv4 or IPv6 address string.
    readers: Open GeoReaders from open_geodbs().

  Returns:
    Dict with keys (all optional, None if not available):
      country_code  - ISO 3166-1 alpha-2 (e.g. 'DE')
      country_name  - English name (e.g. 'Germany')
      asn           - AS number as string (e.g. 'AS13184')
      asn_org       - Organisation name (e.g. 'Deutsche Telekom')
    Empty dict if no data available.
  """
  result: dict = {}

  # City DB is superset of Country — use it first if available
  country_reader = readers.city or readers.country
  if country_reader:
    try:
      rec = country_reader.get(ip_str)
      if rec:
        country = rec.get("country") or rec.get("registered_country", {})
        result["country_code"] = country.get("iso_code")
        names = country.get("names", {})
        result["country_name"] = names.get("en")
        if readers.city and rec.get("city"):
          city_names = rec["city"].get("names", {})
          result["city"] = city_names.get("en")
    except Exception as exc:
      logger.debug("GeoIP country/city lookup failed for %s: %s", ip_str, exc)

  if readers.asn:
    try:
      rec = readers.asn.get(ip_str)
      if rec:
        asn_num = rec.get("autonomous_system_number")
        result["asn"]     = f"AS{asn_num}" if asn_num else None
        result["asn_org"] = rec.get("autonomous_system_organization")
    except Exception as exc:
      logger.debug("GeoIP ASN lookup failed for %s: %s", ip_str, exc)

  return result


def lookup_domain(domain: str, readers: GeoReaders) -> dict:
  """Resolve domain to IP and look up GeoIP data.

  Uses the system resolver — no DNS provider involved.
  Takes the first resolved IPv4 address for lookup.

  Args:
    domain: Fully qualified domain name.
    readers: Open GeoReaders from open_geodbs().

  Returns:
    GeoIP dict from lookup_ip(), or empty dict on failure.
  """
  try:
    # prefer IPv4 for GeoIP lookup — more reliable coverage
    results = socket.getaddrinfo(domain, None, socket.AF_INET)
    if not results:
      results = socket.getaddrinfo(domain, None)
    ip = results[0][4][0]
    return lookup_ip(ip, readers)
  except Exception as exc:
    logger.debug("GeoIP domain resolve failed for %s: %s", domain, exc)
    return {}


def format_geo(geo: dict) -> str:
  """Format GeoIP result as compact display string.

  Args:
    geo: Dict from lookup_ip() or lookup_domain().

  Returns:
    Compact string e.g. 'DE/AS13184 Deutsche Telekom', or empty string.
  """
  if not geo:
    return ""

  parts = []
  loc = geo.get("country_code", "")
  if geo.get("city"):
    loc += f"/{geo['city']}"
  if loc:
    parts.append(loc)
  if geo.get("asn"):
    asn_str = geo["asn"]
    if geo.get("asn_org"):
      asn_str += f" {geo['asn_org']}"
    parts.append(asn_str)

  return " ".join(parts) if parts else ""


def close_geodbs(readers: GeoReaders | None) -> None:
  """Close open MMDB reader handles.

  Args:
    readers: GeoReaders from open_geodbs(), or None.
  """
  if readers is None:
    return
  for reader in [readers.city, readers.country, readers.asn]:
    if reader:
      try:
        reader.close()
      except Exception:
        pass
