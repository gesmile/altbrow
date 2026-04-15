# tests/test_cache.py

import pytest
from pathlib import Path
from altbrow.cache import get_or_build_cache, lookup_domain, lookup_ip


DATA_DIR    = Path(__file__).parent / "data"
CONFIG_PATH = DATA_DIR / "altbrow.toml"


@pytest.fixture(scope="module")
def cache(mock_server, tmp_path_factory):
  """Build cache once for all tests in this module.

  Requires mock_server (from conftest.py) — provider.toml references
  http://localhost:8080/ipfire-ads.txt and fail2ban.txt.
  """
  from altbrow.config import load_provider_config, load_toml

  cache_path = tmp_path_factory.mktemp("cache") / ".altbrow.cache"
  config     = load_toml(CONFIG_PATH)
  provider   = load_provider_config(CONFIG_PATH, config)
  get_or_build_cache(cache_path, provider, CONFIG_PATH)
  return cache_path


# ---------------------------------------------------------------------------
# Basic cache health
# ---------------------------------------------------------------------------

def test_cache_exists(cache):
  """Cache file must exist after build."""
  assert cache.exists()
  assert cache.stat().st_size > 0


# ---------------------------------------------------------------------------
# Inline provider lookups
# ---------------------------------------------------------------------------

def test_lookup_infrastructure(cache):
  """schema.org must be classified as infrastructure."""
  results = lookup_domain("schema.org", cache)
  assert "infrastructure" in [r["category"] for r in results]


def test_lookup_cdn(cache):
  """cdnjs.cloudflare.com must be classified as cdn."""
  results = lookup_domain("cdnjs.cloudflare.com", cache)
  assert "cdn" in [r["category"] for r in results]


def test_lookup_analytics(cache):
  """google-analytics.com must be classified as analytics."""
  results = lookup_domain("google-analytics.com", cache)
  assert "analytics" in [r["category"] for r in results]


def test_lookup_multiple_categories(cache):
  """doubleclick.net must match both tracking and ads."""
  results = lookup_domain("doubleclick.net", cache)
  categories = [r["category"] for r in results]
  assert "tracking" in categories
  assert "ads" in categories


def test_lookup_subdomain_match(cache):
  """Subdomain of known domain matches via registrable domain."""
  results = lookup_domain("sub.google-analytics.com", cache)
  assert "analytics" in [r["category"] for r in results]


def test_lookup_unknown_domain(cache):
  """Unknown domain returns empty list."""
  results = lookup_domain("totally-unknown-xyz123.example", cache)
  assert results == []


# ---------------------------------------------------------------------------
# IP lookups
# ---------------------------------------------------------------------------

def test_lookup_ip_exact(cache):
  """Exact IP match against RFC1918."""
  results = lookup_ip("192.168.1.1", cache)
  assert "local" in [r["category"] for r in results]


def test_lookup_ip_cidr(cache):
  """IP within CIDR block matches."""
  results = lookup_ip("10.0.0.1", cache)
  assert "local" in [r["category"] for r in results]


def test_lookup_ip_unknown(cache):
  """Public IP with no match returns empty list."""
  results = lookup_ip("1.2.3.4", cache)
  assert results == []


def test_no_duplicates(cache):
  """Each (category, provider) pair appears only once per domain."""
  results = lookup_domain("doubleclick.net", cache)
  seen = set()
  for r in results:
    key = (r["category"], r["provider"])
    assert key not in seen, f"Duplicate entry: {key}"
    seen.add(key)


# ---------------------------------------------------------------------------
# Glob provider — provider.d/domain_*.txt and ip_*.txt
# ---------------------------------------------------------------------------

def test_glob_domain_plain_format(cache):
  """Domain from provider.d/domain_local.txt (plain format) must be found."""
  results = lookup_domain("test-local-domain.example.com", cache)
  assert results, "Expected match from local glob provider"
  assert "suspicious" in [r["category"] for r in results]


def test_glob_domain_hosts_format(cache):
  """Domain from provider.d/domain_hosts.txt (hosts format) must be found."""
  results = lookup_domain("test-hosts-domain.example.com", cache)
  assert results, "Expected match from hosts-format local file"
  assert "suspicious" in [r["category"] for r in results]


def test_glob_ip_cidr(cache):
  """IP within CIDR from provider.d/ip_suspicious.txt must match."""
  results = lookup_ip("185.220.101.5", cache)
  assert results, "Expected CIDR match from local IP glob provider"
  assert "suspicious" in [r["category"] for r in results]


def test_glob_ip_exact(cache):
  """Exact IP from provider.d/ip_suspicious.txt must match."""
  results = lookup_ip("5.188.206.14", cache)
  assert results, "Expected exact IP match from local IP glob provider"
  assert "suspicious" in [r["category"] for r in results]


# ---------------------------------------------------------------------------
# Tier-overwrite: local (tier 1) beats remote (tier 2)
# ---------------------------------------------------------------------------

def test_tier_overwrite_local_wins(cache):
  """edjsl.hierbasorganicas.com.mx is in both remote (tier 2) and local (tier 1).

  The result from local-domains provider must appear with lower tier.
  """
  results = lookup_domain("edjsl.hierbasorganicas.com.mx", cache)
  assert results, "Domain must be found in cache"
  tiers = [r["tier"] for r in results]
  assert min(tiers) <= 1, f"Expected tier <=1 from local provider, got: {tiers}"


def test_tier_overwrite_providers_present(cache):
  """Both local and remote provider results must be present for overwrite domain."""
  results = lookup_domain("edjsl.hierbasorganicas.com.mx", cache)
  providers = [r["provider"] for r in results]
  assert "local-domains" in providers, "local-domains provider must be present"
  assert "mock-domain" in providers,   "mock-domain (remote) provider must be present"


# ---------------------------------------------------------------------------
# Special tier-0 provider
# ---------------------------------------------------------------------------

def test_special_tier0(cache):
  """vmtrk.com from special.db must have tier 0."""
  results = lookup_domain("vmtrk.com", cache)
  assert results, "vmtrk.com must be found"
  tiers = {r["tier"] for r in results}
  assert 0 in tiers, f"Expected tier 0 from local-special provider, got: {tiers}"
