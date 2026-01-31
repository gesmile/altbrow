from pathlib import Path
import tomllib


class ConfigError(Exception):
  pass


def load_config(path: str = "config/signals.toml") -> dict:
  config_path = Path(path)

  if not config_path.exists():
    raise ConfigError(f"Config not found: {path}")

  with config_path.open("rb") as f:
    config = tomllib.load(f)

  # Minimal-Validierung
  if "domains" not in config:
    raise ConfigError("Missing [domains] section in config")

  return config

def get_client_profile(config: dict, override: str | None) -> dict:
    client_cfg = config.get("client", {})
    default = client_cfg.get("default_profile", "passive")

    profile_name = override or default
    profiles = client_cfg.get("profiles", {})

    if profile_name not in profiles:
        raise ConfigError(f"Unknown client profile: {profile_name}")

    return profiles[profile_name]
