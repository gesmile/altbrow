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


# ---------------------------------------------------------------------------
# URL-first TSV parser (parse_entries unit test)
# ---------------------------------------------------------------------------

def test_parse_entries_tsv_url_first():
  """parse_entries() extracts hostname from a URL-first TSV line."""
  from altbrow.fetch_remote import parse_entries
  text = "https://www.fbk.eu/en/\tFondazione Bruno Kessler\tResearch institute\t376539"
  result = parse_entries(text)
  assert result == ["www.fbk.eu"]


def test_parse_entries_tsv_http_url():
  """parse_entries() handles http:// URL-first lines."""
  from altbrow.fetch_remote import parse_entries
  text = "http://www.ijcai.org/\tIJCAI\tBiennial AI conference.\t376500"
  result = parse_entries(text)
  assert result == ["www.ijcai.org"]


def test_parse_entries_tsv_mixed_with_plain():
  """parse_entries() handles a file mixing plain domains and URL-first lines."""
  from altbrow.fetch_remote import parse_entries
  text = "example.com\nhttps://www.test.org/path\tTitle\t123"
  result = parse_entries(text)
  assert "example.com" in result
  assert "www.test.org" in result


# ---------------------------------------------------------------------------
# Curlie TSV provider — domains from rdf-*-c.tsv via cache
# ---------------------------------------------------------------------------

def test_curlie_domain_in_cache(cache):
  """Domain from curlie TSV (rdf-Top-c.tsv) must be found as social."""
  results = lookup_domain("www.fbk.eu", cache)
  assert results, "www.fbk.eu must be found via curlie provider"
  assert any(r["provider"] == "curlie" for r in results)
  assert any(r["category"] == "social" for r in results)


# ---------------------------------------------------------------------------
# Bookmark HTML provider — domains and IPs from bookmarks.html via cache
# ---------------------------------------------------------------------------

def test_bookmark_domain_in_cache(cache):
  """Domain from bookmarks.html must be found as local via bookmarks provider."""
  results = lookup_domain("www.heise.de", cache)
  assert results, "www.heise.de must be found via bookmarks provider"
  assert any(r["provider"] == "bookmarks" for r in results)
  assert any(r["category"] == "local" for r in results)


def test_bookmark_ip_in_cache(cache):
  """IP from bookmarks.html must appear with bookmarks-ip provider."""
  results = lookup_ip("192.168.1.1", cache)
  assert results, "192.168.1.1 must be found"
  assert any(r["provider"] == "bookmarks-ip" for r in results)


# ---------------------------------------------------------------------------
# _detect_delimiter() unit tests
# ---------------------------------------------------------------------------

def test_detect_delimiter_tab():
  """Tab is detected before other delimiters."""
  from altbrow.fetch_remote import _detect_delimiter
  assert _detect_delimiter("https://example.com\tTitle\tDesc") == "\t"


def test_detect_delimiter_space():
  """Space is detected when no tab is present."""
  from altbrow.fetch_remote import _detect_delimiter
  assert _detect_delimiter("0.0.0.0 example.com") == " "


def test_detect_delimiter_semicolon():
  """Semicolon is detected when no tab or space is present."""
  from altbrow.fetch_remote import _detect_delimiter
  assert _detect_delimiter("example.com;Title;Desc") == ";"


def test_detect_delimiter_comma():
  """Comma is detected when no tab, space, or semicolon is present."""
  from altbrow.fetch_remote import _detect_delimiter
  assert _detect_delimiter("example.com,Title") == ","


def test_detect_delimiter_fallback():
  """Plain domain with no delimiter returns tab as fallback."""
  from altbrow.fetch_remote import _detect_delimiter
  assert _detect_delimiter("example.com") == "\t"


# ---------------------------------------------------------------------------
# parse_entries() — new format tests
# ---------------------------------------------------------------------------

def test_parse_entries_hosts_format():
  """parse_entries() extracts domain from 0.0.0.0, 127.0.0.1, :: and ::1 hosts lines."""
  from altbrow.fetch_remote import parse_entries
  text = (
    "0.0.0.0 hosts-domain.example.com\n"
    "127.0.0.1 another.example.com\n"
    ":: ipv6-hosts.example.com\n"
    "::1 ipv6-loopback.example.com"
  )
  result = parse_entries(text, provider_type="domain")
  assert "hosts-domain.example.com" in result
  assert "another.example.com" in result
  assert "ipv6-hosts.example.com" in result
  assert "ipv6-loopback.example.com" in result


def test_parse_entries_hosts_multidomain():
  """parse_entries() extracts all domains from a multi-domain hosts line."""
  from altbrow.fetch_remote import parse_entries
  text = "0.0.0.0 one.example.com two.example.com three.example.com"
  result = parse_entries(text, provider_type="domain")
  assert result == ["one.example.com", "two.example.com", "three.example.com"]


def test_parse_entries_hosts_multispaces():
  """parse_entries() handles multiple spaces/tabs between IP and hostname."""
  from altbrow.fetch_remote import parse_entries
  text = "127.0.0.1\t\tcryptomator-vault\n127.0.0.1        another.local"
  result = parse_entries(text, provider_type="domain")
  assert "cryptomator-vault" in result
  assert "another.local" in result


def test_parse_entries_hosts_no_provider_type_returns_ip():
  """Without provider_type, first column is returned as-is (no hosts detection)."""
  from altbrow.fetch_remote import parse_entries
  text = "::1 localhost\n"
  result = parse_entries(text)
  assert "::1" in result
  assert "localhost" not in result


def test_parse_entries_ip_provider_skips_hosts_detection():
  """provider_type='ip' must not trigger hosts detection even if first col is an IP."""
  from altbrow.fetch_remote import parse_entries
  text = "0.0.0.0 some.domain\n1.2.3.4\n"
  result = parse_entries(text, provider_type="ip")
  assert "0.0.0.0" in result
  assert "1.2.3.4" in result
  assert "some.domain" not in result


def test_parse_entries_semicolon_csv():
  """parse_entries() extracts first column from semicolon-delimited CSV."""
  from altbrow.fetch_remote import parse_entries
  text = "semi-domain.example.com;Title;Description"
  result = parse_entries(text)
  assert result == ["semi-domain.example.com"]


def test_parse_entries_quoted_csv():
  """parse_entries() strips quotes from comma-delimited CSV fields."""
  from altbrow.fetch_remote import parse_entries
  text = '"quoted-domain.example.com","Title"'
  result = parse_entries(text)
  assert result == ["quoted-domain.example.com"]


def test_parse_entries_deduplication():
  """parse_entries() deduplicates entries within the same file."""
  from altbrow.fetch_remote import parse_entries
  text = "example.com\nexample.com\nExample.COM"
  result = parse_entries(text)
  assert result.count("example.com") == 1


def test_parse_entries_inline_comment():
  """parse_entries() strips inline # comments from plain domain lines."""
  from altbrow.fetch_remote import parse_entries
  text = "example.com # this is a comment"
  result = parse_entries(text)
  assert result == ["example.com"]


def test_parse_entries_source_name_param():
  """parse_entries() accepts source_name without error."""
  from altbrow.fetch_remote import parse_entries
  text = "example.com\nother.example.com"
  result = parse_entries(text, source_name="test-fixture.txt")
  assert "example.com" in result
  assert "other.example.com" in result


def test_parse_entries_broken_entries_graceful():
  """Malformed entries (empty URL, blank lines, only comments) are silently skipped."""
  from altbrow.fetch_remote import parse_entries
  text = "\n".join([
    "# all comments, no data below until valid entry",
    "# another comment",
    "",
    "https://",                           # URL with no extractable hostname
    "",
    "valid.example.com",
    "https://also-valid.example.org/path",
  ])
  result = parse_entries(text)
  assert "valid.example.com" in result
  assert "also-valid.example.org" in result
  assert all(e for e in result), "no empty strings in result"


# ---------------------------------------------------------------------------
# dns-resolve-filter gates DNS lookup at runtime
# ---------------------------------------------------------------------------

def test_dns_filter_skips_clean_domain(cache, monkeypatch):
  """With dns-resolve-filter set, a clean domain (no static hit) must not trigger DNS."""
  called = []
  monkeypatch.setattr("altbrow.dns_lookup.dns_provider_lookup", lambda d, c: called.append(d) or [])
  config = {"dns-resolve-filter": {"enabled-categories": ["ads", "tracking"], "filter-mode": "or"}}
  lookup_domain("totally-unknown-xyz123.example", cache, config)
  assert "totally-unknown-xyz123.example" not in called


def test_dns_filter_queries_matching_domain(cache, monkeypatch):
  """With dns-resolve-filter for 'ads', a domain already classified as ads must trigger DNS."""
  called = []
  monkeypatch.setattr("altbrow.dns_lookup.dns_provider_lookup", lambda d, c: called.append(d) or [])
  config = {"dns-resolve-filter": {"enabled-categories": ["ads"], "filter-mode": "or"}}
  lookup_domain("doubleclick.net", cache, config)
  assert "doubleclick.net" in called


def test_dns_filter_skips_non_matching_category(cache, monkeypatch):
  """With dns-resolve-filter for 'malware', a domain classified as 'analytics' must skip DNS."""
  called = []
  monkeypatch.setattr("altbrow.dns_lookup.dns_provider_lookup", lambda d, c: called.append(d) or [])
  config = {"dns-resolve-filter": {"enabled-categories": ["malware"], "filter-mode": "or"}}
  lookup_domain("google-analytics.com", cache, config)
  assert "google-analytics.com" not in called


def test_no_dns_filter_queries_all(cache, monkeypatch):
  """Without dns-resolve-filter, DNS must be queried for all domains, including clean ones."""
  called = []
  monkeypatch.setattr("altbrow.dns_lookup.dns_provider_lookup", lambda d, c: called.append(d) or [])
  config = {"provider": {}}  # non-empty config, no dns-resolve-filter key
  lookup_domain("totally-unknown-xyz123.example", cache, config)
  assert "totally-unknown-xyz123.example" in called


@pytest.mark.xfail(
  reason=(
    "is_hosts flag is determined once from the first data line; "
    "when the first line is a plain domain, is_hosts=False and subsequent hosts-format "
    "lines are not split correctly — the whole line is returned verbatim"
  ),
  strict=True,
)
def test_parse_entries_mixed_plain_then_hosts():
  """Known limitation: plain-domain-first file breaks hosts parsing for later lines."""
  from altbrow.fetch_remote import parse_entries
  # First line has no IP → is_hosts=False for the whole file.
  # The second line is a valid hosts entry, but is_hosts is already False,
  # so "hosts-after-plain.example.com" is NOT extracted.
  text = "plain-domain.example.com\n0.0.0.0 hosts-after-plain.example.com"
  result = parse_entries(text, provider_type="domain")
  assert "plain-domain.example.com" in result
  assert "hosts-after-plain.example.com" in result  # fails — hosts line not parsed


# ---------------------------------------------------------------------------
# parse_entries() — ABP filter format tests
# ---------------------------------------------------------------------------

def test_parse_entries_abp_basic():
  """parse_entries() extracts domain from ||domain^ ABP rules."""
  from altbrow.fetch_remote import parse_entries
  text = "||example-ads.com^\n||tracking.net^"
  result = parse_entries(text)
  assert "example-ads.com" in result
  assert "tracking.net" in result


def test_parse_entries_abp_ignores_comments():
  """parse_entries() ignores ! comments and [Section] headers in ABP files."""
  from altbrow.fetch_remote import parse_entries
  text = "[Adblock Plus]\n! Comment line\n||valid-domain.com^"
  result = parse_entries(text)
  assert result == ["valid-domain.com"]


def test_parse_entries_abp_trailing_dot():
  """parse_entries() handles ||domain. wildcard-prefix notation."""
  from altbrow.fetch_remote import parse_entries
  text = "||example.com."
  result = parse_entries(text)
  assert "example.com" in result


def test_parse_entries_abp_ignores_no_tld():
  """parse_entries() skips ABP entries without a dot (e.g. ||localhost^)."""
  from altbrow.fetch_remote import parse_entries
  text = "||nodot^\n||valid.com^"
  result = parse_entries(text)
  assert "valid.com" in result
  assert "nodot" not in result


# ---------------------------------------------------------------------------
# ABP provider — integration test via cache
# ---------------------------------------------------------------------------

def test_abp_domain_in_cache(cache):
  """Domain from ABP-format oisd-small file must be classified as ads."""
  results = lookup_domain("0-02.net", cache)
  assert results, "0-02.net from small.oisd.nl.txt must be found in cache"
  assert any(r["category"] == "ads" for r in results)
  assert any(r["provider"] == "oisd-small" for r in results)
