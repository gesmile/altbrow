# tests/test_integration.py
#
# Integration tests for altbrow domain/IP classification.
# Uses the mock HTTP server from conftest.py serving tests/data/test.html.

import pytest
from pathlib import Path


def _get_domains(extracted: dict) -> dict[str, dict]:
  """Return external_domains as {value: result_dict}."""
  return {
    d["value"]: d
    for d in extracted.get("signals", {}).get("external_domains", [])
  }


def _categories(domain_result: dict) -> list[str]:
  """Return list of category names for a domain result."""
  return [c["category"] for c in domain_result.get("categories", [])]


@pytest.fixture(scope="module")
def extracted(mock_server, tmp_path_factory):
  """Fetch and extract test.html from mock server."""
  from altbrow.fetch import fetch_url
  from altbrow.extract import extract_data
  from altbrow.cache import get_or_build_cache
  from altbrow.config import load_toml, get_client_profile, load_provider_config

  # minimal config — no provider, no geoip
  config = {
    "meta": {"version": 1, "created": "2026-01-01", "use-provider": False},
    "client": {
      "profile": "passive",
      "defaults": {
        "follow_redirects": True, "timeout": 5,
        "fetch_subresources": 0, "use_session": False,
        "use_header": False, "accept_cookies": False, "check_cert": True,
      },
      "profiles": {"passive": {}},
    },
    "output": {"explicit_format": "json"},
  }
  config["provider"] = False

  # use temp cache
  cache_path = tmp_path_factory.mktemp("cache") / ".altbrow.cache"
  get_or_build_cache(cache_path, None, Path("."))

  client_profile = config["client"]["defaults"]
  url = f"{mock_server}/test.html"

  fetched   = fetch_url(url, client_profile)
  extracted = extract_data(fetched, cache_path, config)
  return extracted


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

def test_extracted_has_signals(extracted):
  assert "signals" in extracted


def test_external_domains_present(extracted):
  domains = extracted["signals"]["external_domains"]
  assert len(domains) > 0


# ---------------------------------------------------------------------------
# Domain classification — without provider (unknown expected)
# ---------------------------------------------------------------------------

def test_google_analytics_present(extracted):
  domains = _get_domains(extracted)
  assert "www.google-analytics.com" in domains or "google-analytics.com" in domains


def test_facebook_present(extracted):
  domains = _get_domains(extracted)
  assert any("facebook" in k for k in domains)


def test_unknown_domain_present(extracted):
  domains = _get_domains(extracted)
  assert any("example-unknown-domain-xyz" in k for k in domains)


# ---------------------------------------------------------------------------
# IP classification — RFC1918 IPs should appear as external_ips or in domains
# ---------------------------------------------------------------------------

def test_rfc1918_ip_in_output(extracted):
  """RFC1918 IPs linked directly should appear in external_ips or domains."""
  signals = extracted["signals"]
  ip_values = [ip["value"] for ip in signals.get("external_ips", [])]
  domain_values = [d["value"] for d in signals.get("external_domains", [])]
  all_values = ip_values + domain_values
  # 10.0.0.1 or 192.168.1.1 should appear
  assert any(v.startswith("10.") or v.startswith("192.168.") for v in all_values)


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------

def test_jsonld_detected(extracted):
  jsonld = extracted.get("structured_data", {}).get("json-ld", [])
  assert len(jsonld) > 0


def test_jsonld_type_webpage(extracted):
  jsonld = extracted.get("structured_data", {}).get("json-ld", [])
  types = [b.get("@type") for b in jsonld]
  assert "WebPage" in types
