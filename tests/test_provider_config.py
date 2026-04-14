import tomllib
import re
from pathlib import Path
from altbrow.config import ALLOWED_MAPPINGS

DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")

PROVIDER_TOML = Path(__file__).parent / "data" / "provider.toml"


def test_provider_config_valid():
  """Validate structure and mapping values of all providers in provider.toml."""
  config = tomllib.loads(PROVIDER_TOML.read_text())
  assert "provider" in config

  for name, provider in config["provider"].items():
    assert "location" in provider, f"Provider '{name}' missing 'location'"
    assert "type" in provider,     f"Provider '{name}' missing 'type'"
    assert "enabled" in provider,  f"Provider '{name}' missing 'enabled'"

    if "category" not in provider:
      continue

    for cat in provider.get("category", []):
      assert isinstance(cat["mapping"], list), \
        f"Provider '{name}' mapping must be a list"
      assert all(m in ALLOWED_MAPPINGS for m in cat["mapping"]), \
        f"Provider '{name}' unknown mapping: {cat['mapping']}"


def test_inline_domains():
  """Validate domain syntax for all inline domain providers."""
  config = tomllib.loads(PROVIDER_TOML.read_text())

  for name, provider in config["provider"].items():
    if provider.get("location") != "inline":
      continue
    if provider.get("type") != "domain":
      continue

    for cat in provider.get("category", []):
      for d in cat.get("source", []):
        assert DOMAIN_RE.match(d), \
          f"Provider '{name}' invalid domain '{d}'"