# tests/test_cache.py

import pytest
from pathlib import Path
from altbrow.cache import get_or_build_cache, lookup_domain, lookup_ip


DATA_DIR    = Path(__file__).parent / "data"
CONFIG_PATH = DATA_DIR / "altbrow.toml"
CACHE_PATH  = DATA_DIR / ".altbrow.cache"


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
  """Build cache once for all tests in this module."""
  import tomllib
  from altbrow.config import load_provider_config, load_toml

  cache_path = tmp_path_factory.mktemp("cache") / ".altbrow.cache"
  config      = load_toml(CONFIG_PATH)
  provider    = load_provider_config(CONFIG_PATH, config)
  get_or_build_cache(cache_path, provider, CONFIG_PATH)
  return cache_path


def test_cache_exists(cache):
  """Cache file must exist after build."""
  assert cache.exists()
  assert cache.stat().st_size > 0


def test_lookup_infrastructure(cache):
  """schema.org must be classified as infrastructure."""
  results = lookup_domain("schema.org", cache)
  categories = [r["category"] for r in results]
  assert "infrastructure" in categories


def test_lookup_cdn(cache):
  """cdnjs.cloudflare.com must be classified as cdn."""
  results = lookup_domain("cdnjs.cloudflare.com", cache)
  categories = [r["category"] for r in results]
  assert "cdn" in categories


def test_lookup_analytics(cache):
  """google-analytics.com must be classified as analytics."""
  results = lookup_domain("google-analytics.com", cache)
  categories = [r["category"] for r in results]
  assert "analytics" in categories


def test_lookup_multiple_categories(cache):
  """doubleclick.net must match both tracking and ads."""
  results = lookup_domain("doubleclick.net", cache)
  categories = [r["category"] for r in results]
  assert "tracking" in categories
  assert "ads" in categories


def test_lookup_subdomain_match(cache):
  """Subdomain of known domain matches via registrable domain."""
  results = lookup_domain("sub.google-analytics.com", cache)
  categories = [r["category"] for r in results]
  assert "analytics" in categories


def test_lookup_unknown_domain(cache):
  """Unknown domain returns empty list."""
  results = lookup_domain("totally-unknown-xyz123.example", cache)
  assert results == []


def test_lookup_ip_exact(cache):
  """Exact IP match against RFC1918."""
  results = lookup_ip("192.168.1.1", cache)
  categories = [r["category"] for r in results]
  assert "local" in categories


def test_lookup_ip_cidr(cache):
  """IP within CIDR block matches."""
  results = lookup_ip("10.0.0.1", cache)
  categories = [r["category"] for r in results]
  assert "local" in categories


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
