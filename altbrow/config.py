from pathlib import Path
from altbrow import __version__
from datetime import date
import tomllib

# config.py
#   discover_config_path()
#   load_toml()
#   get_client_profile()
#   validate_altbrow_config()
#   summarize_provider
#   validate_provider_config()

VALID_PROFILES = {"passive", "browser", "consented"}
ALLOWED_LOCATIONS = {"local", "inline", "remote", "dns"}
ALLOWED_TYPES = {"ip", "domain"}
ALLOWED_MAPPINGS = {
    "ads",
    "analytics",
    "cdn",
    "malware",
    "social",
    "suspicious",
    "telemetry",
    "tracking",
    "local",
    "infrastructure",
    "unknown",
}

# Default tier per provider location — lower tier wins (first match in DB on tie)
# Tier 0 is reserved for altbrow internal providers (inlineip, own, infrastructure)
LOCATION_DEFAULT_TIER = {
    "inline": 1,
    "local":  1,
    "dns":    2,
    "remote": 2,
}

class ConfigError(Exception):
  pass

def discover_config_path(cli_path: str | None = None) -> Path:
  """Discover the Altbrow configuration file.

  If no configuration file is found, generates defaults in ~/.altbrow/.

  Args:
    cli_path: CLI given PATH or None.

  Returns:
    Path to the active altbrow.toml.

  Raises:
    ConfigError: If the CLI path/file is not found.

  Search order:
    1. --config PATH  (CLI, explicit)
    2. ./altbrow.toml (portable / development)
    3. ~/.altbrow/altbrow.toml (user, existing or generated)
  """
  # 1. explicit CLI path
  if cli_path:
    path = Path(cli_path).expanduser().resolve()
    if not path.exists():
      raise ConfigError(f"Config not found: {path}")
    return path

  # 2. portable mode — config in current working directory
  local = Path("altbrow.toml")
  if local.exists():
    return local

  # 3. user mode — ~/.altbrow/
  user_dir = Path.home() / ".altbrow"
  user_cfg = user_dir / "altbrow.toml"

  if not user_cfg.exists():
    # first run — generate defaults in ~/.altbrow/
    user_dir.mkdir(parents=True, exist_ok=True)
    user_cfg.write_text(default_config_altbrow(), encoding="utf-8")
    print(f"Created default config: {user_cfg}")

    user_provider = user_dir / "provider.toml"
    if not user_provider.exists():
      user_provider.write_text(default_config_provider(), encoding="utf-8")
      print(f"Created default config: {user_provider}")

  return user_cfg

def load_toml(path: Path) -> dict:
  """Load and parse a TOML file.

  Args:
    path: Absolute or relative path to the TOML file.

  Returns:
    Parsed TOML content as a nested dictionary.

  Raises:
    ConfigError: If the file cannot be read or is not valid TOML.
  """
  try:
    with path.open("rb") as f:
      return tomllib.load(f)
  except Exception as exc:
    raise ConfigError(f"Failed to load config {path}: {exc}") from exc

def get_client_profile(config: dict, override: str | None) -> dict:
  """Resolve the active HTTP client profile from config.

  Merges `[client.defaults]` with the selected profile's overrides.
  The profile is taken from *override* first, then from `client.profile`
  in the config, falling back to `"passive"`.

  Args:
    config: Parsed altbrow config dictionary.
    override: Optional profile name supplied via CLI (`--client-profile`).

  Returns:
    Merged dictionary of client settings for the active profile.

  Raises:
    ConfigError: If no profiles are defined, the profile name is invalid,
      or the named profile does not exist in `[client.profiles]`.
  """
  client_cfg = config.get("client", {})
  defaults = client_cfg.get("defaults", {})
  profiles = client_cfg.get("profiles", {})


  if not profiles:
      raise ConfigError("No client profiles defined in [client.profiles]")

  profile_name = override or client_cfg.get("profile", "passive")

  if profile_name not in VALID_PROFILES:
    raise ConfigError(
      f"Invalid client profile '{profile_name}'. "
      f"Must be one of: {', '.join(sorted(VALID_PROFILES))}"
    )
  if profile_name not in profiles:
    raise ConfigError(
      f"Client profile '{profile_name}' is not defined in [client.profiles]. "
      f"Available: {', '.join(profiles) or 'none'}"
    )

  merged = {**defaults, **profiles[profile_name]}

  # inject [client.headers] if use_header is set in the merged profile
  if merged.get("use_header", False):
    global_headers = client_cfg.get("headers", {})
    if global_headers:
      merged["headers"] = global_headers

  return merged

def default_config_altbrow() -> str:
  return f"""
# default ./altbrow.toml config file

# you may use privat permanent config by moving to:
# ~/.altbrow/altbrow.toml and ~/.altbrow/provider.toml
# if path exsits a Provider cache file will be created there, too

[meta]
version = 1
created = "{date.today()}"
use-provider = false

[validation.schema_org]
allow_unknown_properties = false

[validation]
microdata_vs_jsonld.tolerance = "loose"

[output]
explicit_format = "json"

[client]
profile = "passive"

# **********************
# * profile definition *
# **********************

[client.defaults]
follow_redirects = true       # follow HTTP 301/302
timeout = 10                  # seconds
fetch_subresources = 0        # raw URL, no external javascript, css
use_session = false
use_header = false
accept_cookies = false
check_cert = true

[client.profiles.passive]
# inherits all defaults — no overrides

[client.profiles.browser]
use_session = true
use_header = true

[client.profiles.consented]
use_session = true
use_header = true
accept_cookies = true
fetch_subresources = 1


# Header definition needs periodic update to appear as a normal browser.
# Applied to all profiles where use_header = true.

[client.headers]
"User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
"Accept-Language" = "de-DE,de;q=0.9,en;q=0.8"
# "referer" = "Referer: https://www.google.com/"

"""

def default_config_provider() -> str:
  return f"""
# provider.toml is only used when in "altbrow.toml" is set: `meta.use-provider = true`

# 1st,   given, cli:       --config /etc/altbrow.toml  ->  /etc/provider.toml
# 2nd,   exits, user:      ~/.altbrow/altbrow.toml     ->  ~/.altbrow/provider.toml
# 3rd, default, portable:  ./altbrow.toml              ->  ./provider.toml

# --- 8< ---
# [provider.name]
# name     = "human readable label"            # optional
# location = "[local|inline|remote|dns]"
# type     = "[ip|domain]"
# enabled  = [true|false]
# subdomain_match = [true|false]
#
# # only for dns provider: specific redirect list
# sinkhole = ["<ip>"]     # IP(s) returned for blocked domains
#
# # Every enabled provider needs at least one enabled category:
#
# [[provider.name.category]]
# name    = "human readable label"            # optional
# enabled = [true|false]
# tier    = <int>                              # optional, default: inline/local=1, dns/remote=2
# mapping = ["<category>"]                    # one or more from list below
#
# source  = ["./file.txt"]                    # local: file path(s) relative to provider.toml
# source  = ["example.com"]                   # inline domain: domain list
# source  = ["192.168.1.0/24"]                # inline ip: ip or cidr list
# source  = ["example.com", "iana.org"]       # inline domain: domain list
# source  = ["1.1.1.0/24", "8.8.8.8"]         # inline ip: ip or cidr list
# source  = ["https://example.com/list.txt"]  # remote: URL(s)
# source  = ["<resolver-ip>"]                 # dns: ip list, e.g. openDNS, pihole
# --- 8< ---

# # altbrow internal 8 categories:
#
#   ads           - advertising networks and ad delivery
#   analytics     - user behaviour measurement and reporting
#   cdn           - content delivery networks and static asset hosting
#   malware       - malware, phishing, known hostile domains
#   social        - social networks, dating, gambling, adult content
#   suspicious    - unverified or potentially hostile
#   telemetry     - error reporting, performance monitoring, device telemetry
#   tracking      - cross-site user tracking and profiling

# # altbrow special 3 categories:
#
#   local          - RFC1918, localhost, loopback, your domains
#   infrastructure - technical and semantic web standards, DNS resolvers
#   unknown        - no category match 

# # automatic categories (derived from structure, no provider needed):
#
#   FIRST_PARTY   - same registrable domain (example.com) as the analysed page (e.g. www.example.com)
#   PEER          - siblings like images.example.com
#   SUBDOMAIN     - subdomain of the analysed page domain, e.g. us.www.example.com
#   SELF_REF      - domain appears only in JSON-LD @id / Microdata, not in HTML traffic
#   EXTERNAL      - external domain




[meta]
version = 1
created = "{date.today()}"


# ---------------------------------------------------------------------------
# Local Provider
# ---------------------------------------------------------------------------

[provider.fail2ban]
location = "local"
type     = "ip"
enabled  = false

[[provider.fail2ban.category]]
name    = "fail2ban SSH bans"
mapping = ["suspicious"]
source  = ["./fail2ban.txt"]


# ---------------------------------------------------------------------------
# Inline Domain Providers
# ---------------------------------------------------------------------------

[provider.infrastructure]
location = "inline"
type     = "domain"
enabled  = true

[[provider.infrastructure.category]]
name    = "Semantic Web Standards"
enabled = true
mapping = ["infrastructure"]
source  = [
  "schema.org",
  "schema.googleapis.com",
  "w3.org",
  "w3c.org",
  "purl.org",
  "xmlns.com",
  "rdf.data-vocabulary.org",
  "ogp.me",
  "dublincore.org",
  "json-ld.org",
]

[[provider.infrastructure.category]]
name    = "Web Standards Bodies"
enabled = true
mapping = ["infrastructure"]
source  = [
  "iana.org",
  "mozilla.org",
  "whatwg.org",
]

[provider.cdn]
location = "inline"
type     = "domain"
enabled  = true

[[provider.cdn.category]]
name    = "Example Major CDN"
enabled = true
mapping = ["cdn"]
source  = [
  "cdnjs.cloudflare.com",
  "cdn.cloudflare.com",
  "akamai.net",
  "akamaiedge.net",
  "akamaized.net",
  "edgesuite.net",
  "fastly.net",
  "fastlylb.net",
  "cloudfront.net",
  "amazonaws.com",
  "gstatic.com",
  "azureedge.net",
  "msecnd.net",
  "jsdelivr.net",
  "unpkg.com",
  "bootstrapcdn.com",
  "stackpathcdn.com",
  "b-cdn.net",
  "kxcdn.com",
]

[provider.analytics]
location = "inline"
type     = "domain"
enabled  = true

[[provider.analytics.category]]
name    = "Example Web Analytics"
enabled = true
mapping = ["analytics"]
source  = [
  "google-analytics.com",
  "googletagmanager.com",
  "googleadservices.com",
  "cloudflareinsights.com",
  "matomo.org",
  "plausible.io",
  "fathom.com",
  "segment.com",
  "mixpanel.com",
  "amplitude.com",
  "hotjar.com",
  "clarity.ms",
  "fullstory.com",
  "logrocket.com",
]

[[provider.analytics.category]]
name    = "Example Error and Performance Monitoring"
enabled = true
mapping = ["telemetry"]
source  = [
  "sentry.io",
  "bugsnag.com",
  "rollbar.com",
  "newrelic.com",
  "datadoghq.com",
  "elastic.co",
  "dynatrace.com",
  "appdynamics.com",
]

[provider.tracking]
location = "inline"
type     = "domain"
enabled  = true

[[provider.tracking.category]]
name    = "Example Social Tracking Pixels"
enabled = true
mapping = ["tracking"]
source  = [
  "facebook.net",
  "connect.facebook.net",
  "analytics.twitter.com",
  "t.co",
  "snapchat.com",
  "sc-static.net",
  "ads.pinterest.com",
  "licdn.com",
]

[[provider.tracking.category]]
name    = "Example Ad Network Tracking"
enabled = true
mapping = ["tracking"]
source  = [
  "bat.bing.com",
  "taboola.com",
  "outbrain.com",
  "criteo.com",
  "adroll.com",
  "quantserve.com",
  "scorecardresearch.com",
  "bluekai.com",
  "zemanta.com",
  "doubleclick.net",
]


[provider.ads]
location = "inline"
type     = "domain"
enabled  = true

[[provider.ads.category]]
name    = "Example Ad Delivery"
enabled = true
mapping = ["ads"]
source  = [
  "googlesyndication.com",
  "googleadservices.com",
  "doubleclick.net",
  "amazon-adsystem.com",
  "media.net",
  "moatads.com",
  "adsrvr.org",
  "advertising.com",
  "adnxs.com",
  "rubiconproject.com",
  "pubmatic.com",
  "openx.net",
  "smartadserver.com",
]

# ---------------------------------------------------------------------------
# Inline IP Provider
# ---------------------------------------------------------------------------

[provider.inlineip]
location = "inline"
type     = "ip"
enabled  = true

[[provider.inlineip.category]]
name    = "RFC1918 Private"
enabled = true
mapping = ["local"]
source  = [
  "10.0.0.0/8",
  "172.16.0.0/12",
  "192.168.0.0/16",
]

[[provider.inlineip.category]]
name    = "Loopback"
enabled = true
mapping = ["local"]
source  = [
  "127.0.0.0/8",
  "::1/128",
]

[[provider.inlineip.category]]
name    = "Link-Local and Multicast"
enabled = true
mapping = ["infrastructure"]
source  = [
  "169.254.0.0/16",
  "224.0.0.0/4",
  "255.255.255.255/32",
  "fe80::/10",
  "ff00::/8",
]

[[provider.inlineip.category]]
name    = "Carrier-Grade NAT"
enabled = true
mapping = ["infrastructure"]
source  = [
  "100.64.0.0/10",
]

[[provider.inlineip.category]]
name    = "Example suspicious IPs"
enabled = true
mapping = ["suspicious"]
source  = [
  "2.57.122.210",
  "46.101.74.113",
  "81.192.46.45",
  "92.118.39.56",
  "92.118.39.72",
  "92.118.39.76",
  "102.88.137.80",
  "118.193.36.205",
  "162.223.91.130",
  "193.32.162.151",
  "197.5.145.102",
]

# ---------------------------------------------------------------------------
# Remote Provider
# ---------------------------------------------------------------------------

[provider.ipfire]
location = "remote"
type     = "domain"
enabled  = false

[[provider.ipfire.category]]
name    = "Advertising"
enabled = false
mapping = ["ads"]
source  = ["https://dbl.ipfire.org/lists/ads/domains.txt"]

[[provider.ipfire.category]]
name    = "Dating"
enabled = false
mapping = ["social"]
source  = ["https://dbl.ipfire.org/lists/dating/domains.txt"]

[[provider.ipfire.category]]
name    = "DNS-over-HTTPS"
enabled = false
mapping = ["telemetry"]
source  = ["https://dbl.ipfire.org/lists/doh/domains.txt"]

[[provider.ipfire.category]]
name    = "Gambling"
enabled = false
mapping = ["social"]
source  = ["https://dbl.ipfire.org/lists/gambling/domains.txt"]

[[provider.ipfire.category]]
name    = "Malware"
enabled = false
mapping = ["malware"]
source  = ["https://dbl.ipfire.org/lists/malware/domains.txt"]

[[provider.ipfire.category]]
name    = "Phishing"
enabled = false
mapping = ["malware"]
source  = ["https://dbl.ipfire.org/lists/phishing/domains.txt"]

[[provider.ipfire.category]]
name    = "Piracy"
enabled = false
mapping = ["suspicious"]
source  = ["https://dbl.ipfire.org/lists/piracy/domains.txt"]

[[provider.ipfire.category]]
name    = "Pornography"
enabled = false
mapping = ["social"]
source  = ["https://dbl.ipfire.org/lists/porn/domains.txt"]

[[provider.ipfire.category]]
name    = "Smart TV Telemetry"
enabled = false
mapping = ["telemetry"]
source  = ["https://dbl.ipfire.org/lists/smart-tv/domains.txt"]

[[provider.ipfire.category]]
name    = "Social Networks"
enabled = false
mapping = ["social"]
source  = ["https://dbl.ipfire.org/lists/social/domains.txt"]

[[provider.ipfire.category]]
name    = "Violence"
enabled = false
mapping = ["social"]
source  = ["https://dbl.ipfire.org/lists/violence/domains.txt"]


# ---------------------------------------------------------------------------
# DNS Provider
# resolver and sinkhole are defined on provider level, not category level
# ---------------------------------------------------------------------------

# DNS Provider 

[provider.opendns]
location = "dns"
type = "domain"
enabled = false
resolver = ["208.67.222.222", "208.67.220.220"]
sinkhole = ["146.112.61.106", "146.112.61.107"]

[[provider.opendns.category]]
name = "OpenDNS Sinkhole"
mapping = ["malware"]


[provider.pihole]
location = "dns"
type = "domain"
enabled = false
resolver = ["192.168.1.1"]
sinkhole = ["0.0.0.0", "::"]   # PiHole default

[[provider.pihole.category]]
name = "PiHole local"
mapping = ["ads"]

"""

def load_provider_config(main_config_path: Path, alt_config: dict) -> dict | None:
  """Load `provider.toml` relative to `altbrow.toml` when provider support is enabled.

  Reads `meta.use-provider` from the main config. If `false` (default),
  returns `None` without touching the filesystem.

  Args:
    main_config_path: Path to the active `altbrow.toml` file.
    alt_config: Parsed altbrow config dictionary (used to check `meta.use-provider`).

  Returns:
    Parsed provider config dictionary, or `None` if provider support is disabled.

  Raises:
    ConfigError: If provider support is enabled but `provider.toml` does not exist,
      or if the file cannot be parsed.
  """

  meta = alt_config.get("meta", {})
  use_provider = meta.get("use-provider", False)

  if not use_provider:
    return None

  provider_path = main_config_path.parent / "provider.toml"

  if not provider_path.exists():
    raise ConfigError(f"Provider config not found: {provider_path}")

  return load_toml(provider_path)

def validate_altbrow_config(config: dict, provider: dict | None = None) -> str:
  """Validate an altbrow config dictionary and return a human-readable summary.

  Checks all required sections (`[meta]`, `[client]`, `[client.profiles]`) and
  optional sections (`[validation]`, `[output]`). When provider support is enabled
  the provider config is validated via `validate_provider_config`.

  Args:
    config: Parsed altbrow config dictionary (from `load_toml`).
    provider: Optional parsed provider config dictionary. Required when
      `meta.use-provider = true`.

  Returns:
    Multi-line string summarizing the active configuration (version, profile,
    output format, provider status).

  Raises:
    ConfigError: On any missing or invalid field.
  """
  # --- meta ---
  if "meta" not in config:
    raise ConfigError("Missing [meta] section")
  meta = config["meta"]

  # --- version ---
  if "version" not in meta:
    raise ConfigError("Missing meta.version")

  config_version = meta["version"]
  config_date = meta.get("created", "unknown")

  # --- Provider ---
  provider_text = ""
  use_provider = meta.get("use-provider", False)
  if not isinstance(use_provider, bool):
    raise ConfigError("meta.use-provider must be boolean")

  if use_provider:
      if provider is None:
          raise ConfigError(
              "Provider configuration enabled but file 'provider.toml' not found"
          )
      validate_provider_config(provider)
      provider_text = summarize_provider(provider)
  else:
      if provider is not None:
        provider_text = "Provider configuration disabled."
      else:
        provider_text =  "Provider configuration disabled and config file missing."

  # --- client ---
  if "client" not in config:
    raise ConfigError("Missing [client] section")

  client = config["client"]

  if "profile" not in client:
    raise ConfigError("Missing client.profile")

  if "profiles" not in client:
    raise ConfigError("Missing [client.profiles] section")

  default_profile = client["profile"]
  profiles = client["profiles"]

  if default_profile not in profiles:
    raise ConfigError(f"Default profile '{default_profile}' not found in client.profiles")

  # --- validation (optional) ---
  validation = config.get("validation", {})

  if "microdata_vs_jsonld" in validation:
    tolerance = validation["microdata_vs_jsonld"].get("tolerance")
    if tolerance not in (None, "strict", "loose"):
      raise ConfigError("validation.microdata_vs_jsonld.tolerance must be 'strict' or 'loose'")

  # --- output ---
  output = config.get("output", {})
  explicit_format = output.get("explicit_format", "json")

  if explicit_format not in ("json", "yaml", "text"):
    raise ConfigError("output.explicit_format must be 'json', 'yaml' or 'text'")

  if explicit_format == "yaml":
    output_text = "YAML"
  elif explicit_format == "json":
    output_text = "JSON"
  else:
    output_text = "text"

  # --- profile description ---
  profile = profiles[default_profile]
  use_session = profile.get("use_session", False)
  headers = profile.get("headers", {})

  activity = "active" if use_session else "passive"
  consented = "with consented headers" if headers else "without consent headers"

 

  # --- description sentence ---
  lines = [
    f"Altbrow Version v{__version__} reads with config Version {config_version} from {config_date} a HTTP URL",
    f"It operates {activity} {consented} and counts domains, cookies, html, jsonld and microdata.",
    f"Default structured output format is {output_text}.",
    f"It {'does' if 'microdata_vs_jsonld' in validation else 'does not'} analyse microdata vs jsonld comparison for the summary.",
    provider_text,
    "Output may be written to STDOUT or to a file depending on CLI options."
  ]

  return "\n".join(lines)

def summarize_provider(provider_cfg: dict) -> str:
  """Summarize active providers and categories grouped by location/tier.

  Output format:
    Provider config: 8 provider (5 inline, 1 local, 1 dns, 1 remote)
    of total 11 provider active with 15 of total 18 categories enabled

  Location order follows default tier: inline/local (tier 1) before dns/remote (tier 2).

  Args:
    provider_cfg: Parsed provider.toml dictionary.

  Returns:
    Multi-line summary string for --validate-config output.
  """
  providers = provider_cfg.get("provider", {})

  pcount_sum = len(providers)
  ccount_sum = 0
  ccount     = 0

  # count enabled providers per location (tier order: inline, local, dns, remote)
  location_order = ["inline", "local", "dns", "remote"]
  loc_counts: dict[str, int] = {loc: 0 for loc in location_order}

  for p in providers.values():
    categories = p.get("category", [])
    ccount_sum += len(categories)
    ccount += sum(1 for c in categories if c.get("enabled", True))

    if p.get("enabled", False):
      loc = p.get("location", "remote")
      loc_counts[loc] = loc_counts.get(loc, 0) + 1

  pcount = sum(loc_counts.values())

  # build location breakdown string — only non-zero locations
  loc_parts = [
    f"{v} {k}" for k, v in loc_counts.items() if v > 0
  ]
  loc_str = f" ({', '.join(loc_parts)})" if loc_parts else ""

  return (
    f"Provider config: {pcount}{loc_str} of total {pcount_sum} provider active "
    f"with {ccount} of total {ccount_sum} categories enabled"
  )

def _as_list(value):
  if isinstance(value, list):
    return value
  return [value]

def validate_provider_config(cfg: dict) -> None:

  # --- meta ---
  if "meta" not in cfg:
    raise ConfigError("Missing [meta] section")

  meta = cfg["meta"]

  if "version" not in meta:
    raise ConfigError("Missing meta.version")

  if "created" not in meta:
    raise ConfigError("Missing meta.created")

  # --- provider section ---
  providers = cfg.get("provider", {})

  if not isinstance(providers, dict):
    raise ConfigError("[provider] must be a table of named providers")

  for pname, p in providers.items():

    # --- required provider fields ---
    for field in ("location", "type", "enabled"):
      if field not in p:
        raise ConfigError(f"Provider '{pname}' missing '{field}'")

    location = p["location"]
    ptype = p["type"]

    if location not in ALLOWED_LOCATIONS:
      raise ConfigError(f"Provider '{pname}' invalid location '{location}'")

    if ptype not in ALLOWED_TYPES:
      raise ConfigError(f"Provider '{pname}' invalid type '{ptype}'")

    # --- optional subdomain_match ---
    if "subdomain_match" in p:
      if not isinstance(p["subdomain_match"], bool):
        raise ConfigError(f"Provider '{pname}' subdomain_match must be boolean")

    # --- dns-specific fields on provider level (Option A) ---
    if location == "dns":
      if "resolver" not in p:
        raise ConfigError(f"Provider '{pname}' with location 'dns' missing 'resolver'")
      if "sinkhole" not in p:
        raise ConfigError(f"Provider '{pname}' with location 'dns' missing 'sinkhole'")

      resolvers = p["resolver"]
      sinkholes = p["sinkhole"]

      if not isinstance(resolvers, list) or len(resolvers) == 0:
        raise ConfigError(f"Provider '{pname}' resolver must be a non-empty list")
      if not isinstance(sinkholes, list) or len(sinkholes) == 0:
        raise ConfigError(f"Provider '{pname}' sinkhole must be a non-empty list")

      for r in resolvers:
        if not isinstance(r, str):
          raise ConfigError(f"Provider '{pname}' resolver entries must be strings")
      for s in sinkholes:
        if not isinstance(s, str):
          raise ConfigError(f"Provider '{pname}' sinkhole entries must be strings")

    # --- categories (all provider types) ---
    categories = p.get("category")

    if not isinstance(categories, list) or len(categories) == 0:
      raise ConfigError(f"Provider '{pname}' must define at least one category")

    enabled_category_count = 0

    for i, c in enumerate(categories):

      cname = f"{pname}.category[{i}]"

      # --- enabled default ---
      enabled = c.get("enabled", True)

      if enabled:
        enabled_category_count += 1

      # --- tier (optional, defaults to LOCATION_DEFAULT_TIER[location]) ---
      if "tier" in c:
        tier = c["tier"]
        if not isinstance(tier, int) or tier < 0:
          raise ConfigError(f"{cname} tier must be a non-negative integer >= 1 (0 is reserved for altbrow internals)")

      # --- mapping ---
      if "mapping" not in c:
        raise ConfigError(f"{cname} missing 'mapping'")

      mapping = _as_list(c["mapping"])

      for m in mapping:
        if m not in ALLOWED_MAPPINGS:
          raise ConfigError(f"{cname} invalid mapping '{m}'")

      # --- source: not required for dns (resolver/sinkhole on provider level) ---
      if location == "dns":
        continue

      if "source" not in c:
        raise ConfigError(f"{cname} missing 'source'")

      sources = c["source"]

      if not isinstance(sources, list) or len(sources) == 0:
        raise ConfigError(f"{cname}.source must be a non-empty list")

      for src in sources:

        if not isinstance(src, str):
          raise ConfigError(f"{cname}.source entries must be strings")

        if location == "remote":
          if not (src.startswith("http://") or src.startswith("https://")):
            raise ConfigError(f"{cname} remote source must be URL")

        elif location == "local":
          if src.startswith("http://") or src.startswith("https://"):
            raise ConfigError(f"{cname} local source must be file path")

        elif location == "inline":
          if ptype == "domain":
            if "." not in src:
              raise ConfigError(f"{cname} invalid domain '{src}'")

          elif ptype == "ip":
            if not any(ch.isdigit() for ch in src):
              raise ConfigError(f"{cname} invalid ip/cidr '{src}'")

    if p["enabled"] and enabled_category_count == 0:
      raise ConfigError(f"Provider '{pname}' enabled but no category is enabled")
