# altbrow/dns_lookup.py
#
#   dns_provider_lookup()
#   _should_query_category()

import ipaddress
import logging
import socket

from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import RESOLVE_DEFAULTS

logger = logging.getLogger(__name__)


def _should_query_category(
  cat: dict,
  dns_filter: dict,
) -> bool:
  """Determine if a cache result category should trigger a live DNS re-query.

  Used in cache.py lookup_domain() to decide whether a static cache hit
  warrants an additional live DNS verification pass.
  NOT used to gate which DNS providers are queried — all enabled DNS
  providers are always queried unconditionally.

  Args:
    cat: Dict with "mapping" (list[str]) and "tier" (int) keys.
    dns_filter: Parsed [dns-resolve-filter] section, or empty dict if not configured.

  Returns:
    True if this category should trigger a live DNS re-query.
  """
  if not dns_filter:
    return True  # no filter → query all enabled dns categories

  enabled_cats = dns_filter.get("enabled-categories")
  max_tier     = dns_filter.get("max-tier")
  filter_mode  = dns_filter.get("filter-mode", "or")

  cat_mappings = cat.get("mapping", [])
  cat_tier     = cat.get("tier", 2)

  cat_match  = bool(enabled_cats) and any(m in enabled_cats for m in cat_mappings)
  tier_match = max_tier is not None and cat_tier <= max_tier

  # if neither filter is configured → query all
  if not enabled_cats and max_tier is None:
    return True

  if filter_mode == "and":
    if enabled_cats and max_tier is not None:
      return cat_match and tier_match
    if enabled_cats:
      return cat_match
    return tier_match

  # "or" mode
  checks = []
  if enabled_cats:
    checks.append(cat_match)
  if max_tier is not None:
    checks.append(tier_match)
  return any(checks)


def _query_resolver(
  domain: str,
  resolver_ip: str,
  timeout_s: float,
) -> list[str]:
  """Query a single DNS resolver for A/AAAA records of domain.

  Uses getaddrinfo with explicit nameserver via socket — works without
  dnspython by temporarily patching is not possible, so we use a raw
  UDP DNS query via socket for non-os resolvers.

  For "os" resolver: uses socket.getaddrinfo directly.
  For IP resolvers: uses dnspython if available, otherwise skips with warning.

  Args:
    domain: Domain to resolve.
    resolver_ip: IP address string or "os".
    timeout_s: Timeout in seconds.

  Returns:
    List of resolved IP address strings. Empty on failure or timeout.
  """
  if resolver_ip == "os":
    try:
      results = socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)
      return list({r[4][0] for r in results})
    except Exception as exc:
      logger.debug("OS resolver failed for %s: %s", domain, exc)
      return []

  # explicit IP resolver — requires dnspython
  try:
    import dns.resolver
    import dns.exception

    res = dns.resolver.Resolver(configure=False)
    res.nameservers = [resolver_ip]
    res.timeout    = timeout_s
    res.lifetime   = timeout_s

    ips = []
    for qtype in ("A", "AAAA"):
      try:
        answers = res.resolve(domain, qtype)
        ips.extend(str(r) for r in answers)
      except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
              dns.resolver.NoNameservers, dns.exception.Timeout):
        pass
    return ips

  except ImportError:
    logger.warning(
      "dnspython not installed — cannot query resolver %s. "
      "Install with: pip install dnspython",
      resolver_ip,
    )
    return []
  except Exception as exc:
    logger.debug("Resolver %s failed for %s: %s", resolver_ip, domain, exc)
    return []


def _check_sinkhole(resolved_ips: list[str], sinkhole: list[str]) -> bool:
  """Return True if any resolved IP matches a sinkhole entry (exact or IPv4-mapped).

  Args:
    resolved_ips: List of IP strings returned by DNS resolver.
    sinkhole: List of sinkhole IP strings from provider category config.

  Returns:
    True if at least one resolved IP is in the sinkhole list.
  """
  sinkhole_set = set()
  for s in sinkhole:
    sinkhole_set.add(s.lower())
    # normalise ::ffff:x.x.x.x ↔ x.x.x.x
    try:
      addr = ipaddress.ip_address(s)
      if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        sinkhole_set.add(str(addr.ipv4_mapped))
      elif isinstance(addr, ipaddress.IPv4Address):
        sinkhole_set.add(f"::ffff:{addr}")
    except ValueError:
      pass

  for ip in resolved_ips:
    try:
      addr = ipaddress.ip_address(ip)
      if str(addr).lower() in sinkhole_set:
        return True
      if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        if str(addr.ipv4_mapped) in sinkhole_set:
          return True
    except ValueError:
      pass
  return False


def _query_category(
  domain: str,
  pname: str,
  cat: dict,
  timeout_s: float,
) -> dict | None:
  """Query one DNS provider category and return a result dict if blocked.

  Args:
    domain: Domain to check.
    pname: Provider key (e.g. "pihole").
    cat: Category dict with source (resolvers), sinkhole, mapping, name, tier.
    timeout_s: Per-resolver timeout in seconds.

  Returns:
    Category result dict if domain is blocked, None otherwise.
  """
  resolvers = cat.get("source", [])
  sinkhole  = cat.get("sinkhole", [])
  mappings  = cat.get("mapping", [])
  cat_name  = cat.get("name")
  tier      = cat.get("tier", 2)

  if not resolvers or not sinkhole or not mappings:
    return None

  # query resolvers sequentially — first resolver that answers is authoritative,
  # remaining resolvers are skipped (fallback only on timeout/error)
  for resolver_ip in resolvers:
    logger.debug("DNS querying %s via %s", domain, resolver_ip)
    resolved = _query_resolver(domain, resolver_ip, timeout_s)
    if not resolved:
      # timeout or error — try next resolver
      continue
    # first resolver that answered is authoritative
    if _check_sinkhole(resolved, sinkhole):
      logger.debug(
        "DNS block: %s matched %s/%s via %s",
        domain, pname, cat_name, resolver_ip,
      )
      return {
        "category":          mappings[0],
        "provider":          pname,
        "provider_location": "dns",
        "category_name":     cat_name,
        "tier":              tier,
      }
    # not in sinkhole — domain is not blocked by this provider
    return None

  return None


def dns_provider_lookup(
  domain: str,
  config: dict,
) -> list[dict]:
  """Query all enabled DNS provider categories for a domain in parallel.

  All enabled DNS providers are always queried unconditionally.
  dns-resolve-filter does NOT gate which providers are queried here —
  it is used in cache.py to decide whether DNS lookup is triggered at all.

  Args:
    domain: Fully qualified domain name to check.
    config: Merged altbrow config dict (with config["provider"] set).

  Returns:
    List of category result dicts for blocked domains, sorted by tier.
    Empty list if not blocked or no DNS providers active.
  """
  providers = config.get("provider") or {}
  resolve   = config.get("resolve", {})

  timeout_s = float(resolve.get("resolver-timeout", RESOLVE_DEFAULTS["resolver-timeout"]))

  # collect (pname, cat) pairs — all enabled DNS provider categories
  tasks: list[tuple[str, dict]] = []

  for pname, p in providers.items():
    if not isinstance(p, dict):
      continue
    if p.get("location") != "dns":
      continue
    if not p.get("enabled", False):
      continue

    for cat in p.get("category", []):
      if not cat.get("enabled", True):
        continue
      tasks.append((pname, cat))

  if not tasks:
    return []

  results: list[dict] = []

  # parallel queries — one thread per (provider, category) pair
  with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as executor:
    futures = {
      executor.submit(_query_category, domain, pname, cat, timeout_s): (pname, cat)
      for pname, cat in tasks
    }
    for future in as_completed(futures):
      try:
        result = future.result()
        if result:
          results.append(result)
      except Exception as exc:
        pname, cat = futures[future]
        logger.warning("DNS query failed for %s/%s: %s", pname, cat.get("name"), exc)

  return sorted(results, key=lambda r: r.get("tier", 2))