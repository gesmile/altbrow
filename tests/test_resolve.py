# tests/test_resolve_config.py
#
# Tests for [resolve] section validation in provider.toml

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from altbrow.config import validate_provider_config, RESOLVE_DEFAULTS, ConfigError

BASE_CFG = {
    "meta": {"version": 1, "created": "2026-01-01"},
    "provider": {},
}


def cfg_with_resolve(resolve: dict) -> dict:
    return {**BASE_CFG, "resolve": resolve}


# ---------------------------------------------------------------------------
# RESOLVE_DEFAULTS
# ---------------------------------------------------------------------------

def test_resolve_defaults_keys():
    assert "resolve-domains" in RESOLVE_DEFAULTS
    assert "resolver" in RESOLVE_DEFAULTS
    assert "resolver-timeout" in RESOLVE_DEFAULTS


def test_resolve_defaults_values():
    assert RESOLVE_DEFAULTS["resolve-domains"] is False
    assert RESOLVE_DEFAULTS["resolver"] == ["os"]
    assert RESOLVE_DEFAULTS["resolver-timeout"] == 2


# ---------------------------------------------------------------------------
# Missing [resolve] section — should pass with defaults
# ---------------------------------------------------------------------------

def test_no_resolve_section():
    validate_provider_config(BASE_CFG)  # no exception


# ---------------------------------------------------------------------------
# resolve-domains
# ---------------------------------------------------------------------------

def test_resolve_domains_true():
    validate_provider_config(cfg_with_resolve({"resolve-domains": True}))


def test_resolve_domains_false():
    validate_provider_config(cfg_with_resolve({"resolve-domains": False}))


def test_resolve_domains_invalid():
    with pytest.raises(ConfigError, match="resolve.resolve-domains must be boolean"):
        validate_provider_config(cfg_with_resolve({"resolve-domains": "yes"}))


# ---------------------------------------------------------------------------
# resolver
# ---------------------------------------------------------------------------

def test_resolver_os():
    validate_provider_config(cfg_with_resolve({"resolver": ["os"]}))


def test_resolver_ip():
    validate_provider_config(cfg_with_resolve({"resolver": ["1.1.1.1", "8.8.8.8"]}))


def test_resolver_mixed():
    validate_provider_config(cfg_with_resolve({"resolver": ["os", "1.1.1.1"]}))


def test_resolver_ipv6():
    validate_provider_config(cfg_with_resolve({"resolver": ["2620:119:35::35"]}))


def test_resolver_empty_list():
    with pytest.raises(ConfigError, match="non-empty list"):
        validate_provider_config(cfg_with_resolve({"resolver": []}))


def test_resolver_not_list():
    with pytest.raises(ConfigError, match="non-empty list"):
        validate_provider_config(cfg_with_resolve({"resolver": "1.1.1.1"}))


def test_resolver_invalid_entry():
    with pytest.raises(ConfigError, match="invalid entry"):
        validate_provider_config(cfg_with_resolve({"resolver": ["not-an-ip"]}))


# ---------------------------------------------------------------------------
# resolver-timeout
# ---------------------------------------------------------------------------

def test_resolver_timeout_valid():
    validate_provider_config(cfg_with_resolve({"resolver-timeout": 5}))


def test_resolver_timeout_zero():
    with pytest.raises(ConfigError, match="positive integer"):
        validate_provider_config(cfg_with_resolve({"resolver-timeout": 0}))


def test_resolver_timeout_negative():
    with pytest.raises(ConfigError, match="positive integer"):
        validate_provider_config(cfg_with_resolve({"resolver-timeout": -1}))


def test_resolver_timeout_string():
    with pytest.raises(ConfigError, match="positive integer"):
        validate_provider_config(cfg_with_resolve({"resolver-timeout": "2000"}))


# ---------------------------------------------------------------------------
# Full valid [resolve] section
# ---------------------------------------------------------------------------

def test_full_resolve_section():
    validate_provider_config(cfg_with_resolve({
        "resolve-domains":  True,
        "resolver":         ["os", "1.1.1.1"],
        "resolver-timeout": 3,
    }))
