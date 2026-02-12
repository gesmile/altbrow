from pathlib import Path
import tomllib


class ConfigError(Exception):
  """
  Raised when the Altbrow configuration is invalid.
  """
  pass


def load_toml(path: str = "config/altbrow.toml") -> dict:
  """
  Load a TOML configuration file.

  Args:
    path: Path to the TOML file.

  Returns:
    Parsed configuration as a dictionary.

  Raises:
    ConfigError: If the file cannot be loaded.
  """

  config_path = Path(path)

  if not config_path.exists():
    raise ConfigError(f"Config not found: {path}")

  with config_path.open("rb") as f:
    config = tomllib.load(f)

  return config


def get_client_profile(config: dict, override: str | None) -> dict:
  client_cfg = config.get("client", {})
  default = client_cfg.get("default_profile", "passive")

  profile_name = override or default
  profiles = client_cfg.get("profiles", {})

  if profile_name not in profiles:
      raise ConfigError(f"Unknown client profile: {profile_name}")

  return profiles[profile_name]


def validate_altbrow_config(config: dict) -> str:
  # --- meta ---
  if "meta" not in config:
    raise ConfigError("Missing [meta] section")

  if "version" not in config["meta"]:
    raise ConfigError("Missing meta.version")

  version = config["meta"]["version"]

  # --- client ---
  if "client" not in config:
    raise ConfigError("Missing [client] section")

  client = config["client"]

  if "default_profile" not in client:
    raise ConfigError("Missing client.default_profile")

  if "profiles" not in client:
    raise ConfigError("Missing [client.profiles] section")

  default_profile = client["default_profile"]
  profiles = client["profiles"]

  if default_profile not in profiles:
    raise ConfigError(
      f"Default profile '{default_profile}' not found in client.profiles"
    )

  # --- validation (optional but structured) ---
  validation = config.get("validation", {})

  if "microdata_vs_jsonld" in validation:
    tolerance = validation["microdata_vs_jsonld"].get("tolerance")
    if tolerance not in (None, "strict", "loose"):
      raise ConfigError(
        "validation.microdata_vs_jsonld.tolerance must be 'strict' or 'loose'"
      )

  output = config.get("output", {})
  explicit_format = output.get("explicit_format", "json")

  if explicit_format not in ("json", "yaml"):
    raise ConfigError(
      "output.explicit_format must be 'json' or 'yaml'"
    )

  if explicit_format == "yaml":
    output_text = "explicit YAML"
  else:
    output_text = "explicit JSON"

  # --- description sentence ---
  profile = profiles[default_profile]
  use_session = profile.get("use_session", False)
  headers = profile.get("headers", {})

  activity = "active" if use_session else "passive"
  consented = "with consented" if headers else "without consent"

  lines = [
    f"Altbrow reads with config {version} a HTTP URL "
    f"{activity} {consented} and counts domains, cookies, html, jsonld, microdata.",
    f"It writes {output_text} to STDOUT and not to file.",
    f"It {'does' if 'microdata_vs_jsonld' in validation else 'does not'} "
    "analyse for a comparison added to summary.",
    "It does not log to <file>."
    ]
  sentence = "\n".join(lines)

  return sentence
