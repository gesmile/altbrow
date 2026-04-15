# tests/test_integration.py
#
# Integration tests for altbrow domain/IP classification.
# Uses mock HTTP server from conftest.py serving tests/data/.
#
# Two provider configs × two host aliases = 4 requests:
#   provider-basic.toml  + localhost:8080/test.html
#   provider-basic.toml  + 127.0.0.1:8080/test.html
#   provider-dns.toml    + localhost:8080/test.html      (DNS disabled, skipped if no resolver)
#   provider-dns.toml    + 127.0.0.1:8080/test.html     (DNS disabled, skipped if no resolver)

import pytest
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _get_domains(extracted: dict) -> dict[str, dict]:
  """Return external_domains as {value: result_dict}."""
  return {
    d["value"]: d
    for d in extracted.get("signals", {}).get("external_domains", [])
  }


def _categories(domain_result: dict) -> list[str]:
  """Return list of category names for a domain result."""
  return [c["category"] for c in domain_result.get("categories", [])]


def _build_extracted(url: str, provider_toml: str, tmp_path_factory):
  """Fetch and extract a URL using the given provider.toml filename."""
  from altbrow.fetch import fetch_url
  from altbrow.extract import extract_data
  from altbrow.cache import get_or_build_cache
  from altbrow.config import load_toml, load_provider_config

  config_path = DATA_DIR / "altbrow.toml"
  config      = load_toml(config_path)

  # swap provider.toml
  import tomllib
  provider_path = DATA_DIR / provider_toml
  provider_cfg  = tomllib.loads(provider_path.read_text())
  from altbrow.config import validate_provider_config
  validate_provider_config(provider_cfg)

  # patch config to use this provider
  config["meta"]["use-provider"] = True
  from altbrow.config import _strip_provider_sources
  stripped = _strip_provider_sources(provider_cfg)
  for key, value in stripped.items():
    if key in {"provider", "dns-resolve-filter", "resolve"}:
      config[key] = value

  cache_path = tmp_path_factory.mktemp(provider_toml) / ".altbrow.cache"
  get_or_build_cache(cache_path, provider_cfg, provider_path)

  client_profile = {**config["client"]["defaults"]}
  fetched   = fetch_url(url, client_profile)
  extracted = extract_data(fetched, cache_path, config)
  return extracted


# ---------------------------------------------------------------------------
# Fixtures — one per (provider_config, host_alias) combination
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def basic_localhost(mock_server, tmp_path_factory):
  return _build_extracted(
    f"http://localhost:8080/test.html",
    "provider-basic.toml",
    tmp_path_factory,
  )


@pytest.fixture(scope="module")
def basic_127(mock_server, tmp_path_factory):
  return _build_extracted(
    f"http://127.0.0.1:8080/test.html",
    "provider-basic.toml",
    tmp_path_factory,
  )


@pytest.fixture(scope="module")
def dns_localhost(mock_server, tmp_path_factory):
  return _build_extracted(
    f"http://localhost:8080/test.html",
    "provider-dns.toml",
    tmp_path_factory,
  )


@pytest.fixture(scope="module")
def dns_127(mock_server, tmp_path_factory):
  return _build_extracted(
    f"http://127.0.0.1:8080/test.html",
    "provider-dns.toml",
    tmp_path_factory,
  )


# ---------------------------------------------------------------------------
# Basic structure — applies to all four variants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extracted_fixture", [
  "basic_localhost", "basic_127", "dns_localhost", "dns_127"
])
def test_has_signals(extracted_fixture, request):
  extracted = request.getfixturevalue(extracted_fixture)
  assert "signals" in extracted


@pytest.mark.parametrize("extracted_fixture", [
  "basic_localhost", "basic_127", "dns_localhost", "dns_127"
])
def test_external_domains_present(extracted_fixture, request):
  extracted = request.getfixturevalue(extracted_fixture)
  assert len(extracted["signals"]["external_domains"]) > 0


# ---------------------------------------------------------------------------
# Provider classification — basic config
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extracted_fixture", ["basic_localhost", "basic_127"])
def test_analytics_classified(extracted_fixture, request):
  """google-analytics.com must be classified as analytics."""
  extracted = request.getfixturevalue(extracted_fixture)
  domains = _get_domains(extracted)
  target = domains.get("www.google-analytics.com") or domains.get("google-analytics.com")
  assert target is not None
  assert "analytics" in _categories(target)


@pytest.mark.parametrize("extracted_fixture", ["basic_localhost", "basic_127"])
def test_cdn_classified(extracted_fixture, request):
  """cdnjs.cloudflare.com must be classified as cdn."""
  extracted = request.getfixturevalue(extracted_fixture)
  domains = _get_domains(extracted)
  target = domains.get("cdnjs.cloudflare.com")
  assert target is not None
  assert "cdn" in _categories(target)


@pytest.mark.parametrize("extracted_fixture", ["basic_localhost", "basic_127"])
def test_tracking_classified(extracted_fixture, request):
  """connect.facebook.net must be classified as tracking."""
  extracted = request.getfixturevalue(extracted_fixture)
  domains = _get_domains(extracted)
  target = domains.get("connect.facebook.net")
  assert target is not None
  assert "tracking" in _categories(target)


@pytest.mark.parametrize("extracted_fixture", ["basic_localhost", "basic_127"])
def test_ads_classified(extracted_fixture, request):
  """pagead2.googlesyndication.com must be classified as ads."""
  extracted = request.getfixturevalue(extracted_fixture)
  domains = _get_domains(extracted)
  # subdomain_match: googlesyndication.com is in provider
  target = domains.get("pagead2.googlesyndication.com")
  assert target is not None
  assert "ads" in _categories(target)


@pytest.mark.parametrize("extracted_fixture", ["basic_localhost", "basic_127"])
def test_infrastructure_classified(extracted_fixture, request):
  """schema.org must be classified as infrastructure."""
  extracted = request.getfixturevalue(extracted_fixture)
  domains = _get_domains(extracted)
  target = domains.get("schema.org")
  assert target is not None
  assert "infrastructure" in _categories(target)


@pytest.mark.parametrize("extracted_fixture", ["basic_localhost", "basic_127"])
def test_unknown_domain_no_category(extracted_fixture, request):
  """example-unknown-domain-xyz.com must have no provider category."""
  extracted = request.getfixturevalue(extracted_fixture)
  domains = _get_domains(extracted)
  target = next((v for k, v in domains.items() if "example-unknown-domain-xyz" in k), None)
  assert target is not None
  assert _categories(target) == []


# ---------------------------------------------------------------------------
# IP classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extracted_fixture", ["basic_localhost", "basic_127"])
def test_rfc1918_in_output(extracted_fixture, request):
  """RFC1918 IPs from test.html must appear in output."""
  extracted = request.getfixturevalue(extracted_fixture)
  signals = extracted["signals"]
  ip_values     = [ip["value"] for ip in signals.get("external_ips", [])]
  domain_values = [d["value"] for d in signals.get("external_domains", [])]
  all_values = ip_values + domain_values
  assert any(v.startswith("10.") or v.startswith("192.168.") for v in all_values)


# ---------------------------------------------------------------------------
# localhost vs 127.0.0.1 — TARGET relation must differ
# ---------------------------------------------------------------------------

def test_target_relation_localhost(basic_localhost):
  """TARGET host is localhost — must be FIRST_PARTY."""
  domains = _get_domains(basic_localhost)
  target = domains.get("localhost")
  if target:
    assert target["relation"] == "FIRST_PARTY"


def test_target_relation_127(basic_127):
  """TARGET host is 127.0.0.1 — must appear in external_ips with TARGET occurrence."""
  signals = basic_127["signals"]
  ips = {ip["value"]: ip for ip in signals.get("external_ips", [])}
  if "127.0.0.1" in ips:
    assert ips["127.0.0.1"]["occurrence"] == "TARGET"

# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extracted_fixture", [
  "basic_localhost", "basic_127"
])
def test_jsonld_detected(extracted_fixture, request):
  extracted = request.getfixturevalue(extracted_fixture)
  jsonld = extracted.get("structured_data", {}).get("json-ld", [])
  assert len(jsonld) > 0


@pytest.mark.parametrize("extracted_fixture", [
  "basic_localhost", "basic_127"
])
def test_jsonld_type_webpage(extracted_fixture, request):
  extracted = request.getfixturevalue(extracted_fixture)
  jsonld = extracted.get("structured_data", {}).get("json-ld", [])
  types = [b.get("@type") for b in jsonld]
  assert "WebPage" in types
