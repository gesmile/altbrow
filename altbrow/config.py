from pathlib import Path
from altbrow import __version__
from altbrow.utils import format_size
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
ALLOWED_PROTOCOLS = {"https://", "http://"}
ALLOWED_LOCAL_HOSTNAMES = { "localhost", "localhost.localdomain", "local", "ip6-localhost", "ip6-loopback", "broadcasthost", }
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
  "geoip",
}

# Default tier per provider location — lower tier wins (first match in DB on tie)
# Configuration for provider.name.category overwrites.
# If no tier is configured at category level, this browser location mapping is used
LOCATION_DEFAULT_TIER = {
  "inline": 1,
  "local":  1,
  "dns":    2,
  "remote": 2,
}

# Default [resolve] section values for provider.toml
RESOLVE_DEFAULTS: dict = {
  "resolve-domains":  False,
  "resolver":         ["os"],
  "resolver-timeout": 2,
}

# special download and extract strings
_MAJESTIC_DOWNLOAD = (
  r"# Download: curl -s https://downloads.majestic.com/majestic_million.csv"
  r" | awk -F ',' 'NR>1{print $3}'"
  r" > ~/.altbrow/majestic_million.csv"
)

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
  return f"""# default config file: altbrow.toml

# good location: ~/.altbrow/altbrow.toml
# same for provider.toml and cache file location

[meta]
version = 1
created = "{date.today()}"
use-provider = false

[validation]

# for future use: strict schema.org property validation
# schema_org.allow_unknown_properties = false

# for future use: tolerance when same content appears in both microdata and JSON-LD
# microdata_vs_jsonld.tolerance = "loose"   # loose | strict

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
  return f"""# Provider system config: provider.toml

# Activate the provider system by setting `meta.use-provider = true` in altbrow.toml.
# The cache file (.altbrow.cache) is built next to altbrow.toml on first run or via --build-cache.

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# --- 8< ---
# [provider.name]
# name            = "human readable label"            # optional
# location        = "[inline|local|remote|dns]"
# type            = "[ip|domain|geoip]"
# enabled         = [true|false]                      # optional, default: true
# subdomain_match = [true|false]                      # optional, default: true
#   true:  cdn.example.com matches if example.com is in the list (registrable domain)
#   false: only exact hostname matches — recommended for large lists (Curlie, Tranco)

# [[provider.name.category]]
# name     = "human readable label"           # optional
# enabled  = [true|false]                     # optional, default: true
# tier     = <int>                            # optional, default: inline/local=1, dns/remote=2; 0 = highest priority
# mapping  = ["<category>"]                   # one or more from list below
# sinkhole = ["<ip>", ...]                    # dns only: block page IPs for this category
# source   = ["./file.txt"]                   # local: file path(s) relative to altbrow.toml
# source  = ["example.com", "iana.org"]       # inline domain: domain list
# source   = ["1.1.1.0/24", "8.8.8.8"]        # inline ip: ip or cidr list
# source   = ["https://example.com/list.txt"] # remote: URL(s)
# source   = ["<resolver-ip>", ...]           # dns: resolver IP(s) per category
# --- 8< ---

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

# 10 useable categories:
#   ads           - advertising networks and ad delivery
#   analytics     - user behavior measurement and reporting
#   cdn           - content delivery networks and static asset hosting
#   malware       - malware, phishing, known hostile domains
#   social        - social networks, dating, gambling, adult content
#   suspicious    - unverified or potentially hostile
#   telemetry     - error reporting, performance monitoring, device telemetry
#   tracking      - cross-site user tracking and profiling
#   local          - RFC1918, localhost, loopback, your own domains
#   infrastructure - web standards, DNS resolvers, technical endpoints

# config category:
#   geoip          - used for location service, not a regular category

[meta]
version = 1
created = "{date.today()}"

# ---------------------------------------------------------------------------
# Resolve Configuration
# ---------------------------------------------------------------------------

[resolve]
resolve-domains  = false       # resolve domains to IP and check against IP provider lists
resolver         = ["os"]      # "os" = system resolver, or explicit IPs: ["1.1.1.1", "8.8.8.8"]
resolver-timeout = 2           # seconds per DNS query

# ---------------------------------------------------------------------------

# DNS Resolve Filter
# Controls which provider categories trigger a live DNS query.
# Empty section: all enabled DNS provider categories are queried (always DNS even unknown)
# filter-mode = "or"  → category match OR  tier <= max-tier
# filter-mode = "and" → category match AND tier <= max-tier
# Disable all DNS queries: set enabled-categories = [] with filter-mode = "and"
#                          or simply disable all DNS providers below.

[dns-resolve-filter]
# all DNS providers queried unconditionally — uncomment below to filter:
#enabled-categories = ["malware", "suspicious","tracking","ads","analytics","social","telemetry"]
#max-tier    = 2
#filter-mode = "and"

# ---------------------------------------------------------------------------
# Inline Domain Provider — example inline
# ---------------------------------------------------------------------------

[provider.osupdate]
location = "inline"
type     = "domain"
enabled  = true

[[provider.osupdate.category]]
name    = "cdn"
mapping = ["cdn"]
source  = [
  "windowsupdate.com",       # Microsoft
  "swcdn.apple.com",         # macOS
  "deb.debian.org",          # Debian
  ]

# ---------------------------------------------------------------------------
# Local Provider — example filesystem lists
# ---------------------------------------------------------------------------

[provider.fail2ban]
location = "local"
type     = "ip"
enabled  = false

[[provider.fail2ban.category]]
name    = "local"
mapping = ["suspicious"]
source  = ["./fail2ban.txt"]

# ---------------------------------------------------------------------------

# OISD Blacklist (https://oisd.nl) — in ABP Filter Format

[provider.oisd]
location = "remote"
type     = "domain"
enabled  = false

[[provider.oisd.category]]
name    = "big"
mapping = ["ads"]
enabled  = true
source  = ["https://big.oisd.nl"]

[[provider.oisd.category]]
name    = "nsfw"
mapping = ["social"]
enabled  = false
source  = ["https://nsfw.oisd.nl"]

# ---------------------------------------------------------------------------

# HaGeZi's Pro DNS Blocklists (https://github.com/hagezi/dns-blocklists)

[provider.hagezi]
location = "remote"
type     = "domain"
enabled  = false

[[provider.hagezi.category]]
name    = "pro"
mapping = ["tracking"]
tier    = 3
source  = ["https://raw.githubusercontent.com/hagezi/dns-blocklists/main/domains/pro.txt"]

# ---------------------------------------------------------------------------

# Majestic Million - Top 1 million
{_MAJESTIC_DOWNLOAD}
# Powershell: 
#   Invoke-WebRequest -Uri "https://downloads.majestic.com/majestic_million.csv" -OutFile "$env:TEMP\\majestic.csv"
#   Import-Csv "$env:TEMP\\majestic.csv" | Select-Object -ExpandProperty Domain | Set-Content "$env:USERPROFILE\\.altbrow\\majestic_million.csv"

[provider.majestic]
location = "local"
type     = "domain"
enabled  = false

[[provider.majestic.category]]
name    = "1M"
mapping = ["social"]
tier    = 9
source  = ["./majestic_million.csv"]

# ---------------------------------------------------------------------------

# Curlie — largest human-edited web directory: https://curlie.org/download
# Download and extract the tar.gz, use rdf-*-c.tsv files (URL as first column).

[provider.curlie]
location = "local"
type     = "domain"
enabled  = false
subdomain_match = false

[[provider.curlie.category]]
name    = "all"
tier    = 8
mapping = ["social"]
source  = ["./provider.d/rdf-*-c.tsv"]

# ---------------------------------------------------------------------------

# Tranco Top 1M — https://tranco-list.eu/latest_list
# find actual download link: `curl -s https://tranco-list.eu/api/lists/date/latest | python -m json.tool`
# Strip rank column first: sed -i 's/^[0-9]*,//' top-1m.csv

[provider.tranco]
name     = "Tranco"
location = "local"
type     = "domain"
enabled  = false
subdomain_match = false

[[provider.tranco.category]]
name    = "Top 1M"
tier    = 9
mapping = ["social"]
source  = ["./top-1m.csv"]

# ---------------------------------------------------------------------------

# OpenPhish - Relevant Phishing Intelligence.
# free limited use under following Terms of Use: https://openphish.com/terms.html

[provider.openphish]
location = "remote"
type     = "domain"
enabled  = false

[[provider.openphish.category]]
name    = "Limited"
mapping = ["malware"]
source  = ["https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt"]

# ---------------------------------------------------------------------------

# IP Fire - https://www.ipfire.org/
# further categories: dating, dns-over-https, gambling, piracy, porn, smart-tv, social, violence
# see https://dbl.ipfire.org/lists/ for URLs


[provider.ipfire]
name     = "IPFire"
location = "remote"
type     = "domain"
enabled  = false

[[provider.ipfire.category]]
name    = "Malware"
tier    = 1
mapping = ["malware"]
source  = ["https://dbl.ipfire.org/lists/malware/domains.txt"]

[[provider.ipfire.category]]
name    = "Phishing"
tier    = 1
mapping = ["malware"]
source  = ["https://dbl.ipfire.org/lists/phishing/domains.txt"]

[[provider.ipfire.category]]
name    = "Advertising"
enabled = false
tier    = 9
mapping = ["ads"]
source  = ["https://dbl.ipfire.org/lists/ads/domains.txt"]

# ---------------------------------------------------------------------------

# StevenBlack hosts — used by Pi-hole and many other blockers.
# Set sinkhole to your Pi-hole IP if using dns provider below.

[provider.stevenblack]
location = "remote"
type     = "domain"
enabled  = false

[[provider.stevenblack.category]]
name    = "Ads and Malware"
mapping = ["ads"]
source  = ["https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"]

# ---------------------------------------------------------------------------
# DNS Provider - see also `dns-resolve-filter` to pitch DNS queries
# source = resolver IPs per category, sinkhole = block page IPs
# ---------------------------------------------------------------------------

# Pi-hole — set source to your Pi-hole IP, sinkhole to its block page IP (usually 0.0.0.0).
# The StevenBlack remote list above covers the same domains as the default Pi-hole blocklist.

[provider.pihole]
location = "dns"
type     = "domain"
enabled  = false

[[provider.pihole.category]]
name     = "Pi-hole local"
mapping  = ["ads"]
source   = ["192.168.1.1"]          # replace with your Pi-hole IP
sinkhole = ["0.0.0.0", "::", "::ffff:0.0.0.0"]

# ---------------------------------------------------------------------------

# OpenDNS https://www.opendns.com/ is the base of Cisco's Umbrella service

[provider.opendns]
name     = "OpenDNS"
location = "dns"
type     = "domain"
enabled  = false

[[provider.opendns.category]]
name     = "Malware/Phishing"
mapping  = ["malware"]
source   = ["208.67.222.222", "208.67.220.220", "2620:119:35::35", "2620:119:53::53"]
sinkhole = [
  "146.112.61.104", "146.112.61.105", "146.112.61.107", "146.112.61.108",
  "::ffff:146.112.61.104", "::ffff:146.112.61.105",
  "::ffff:146.112.61.107", "::ffff:146.112.61.108",
]

[[provider.opendns.category]]
name     = "Content/Adult (FamilyShield)"
enabled  = false
mapping  = ["social"]
source   = ["208.67.222.123", "208.67.220.123"]
sinkhole = ["146.112.61.106", "::ffff:146.112.61.106"]

[[provider.opendns.category]]
name     = "Suspicious/DNS Tunneling"
enabled  = false
mapping  = ["suspicious"]
source   = ["208.67.222.222", "208.67.220.220", "2620:119:35::35", "2620:119:53::53"]
sinkhole = ["146.112.61.110", "::ffff:146.112.61.110"]


# ---------------------------------------------------------------------------
# GeoIP Provider (MaxMind GeoLite2)
# Download: https://dev.maxmind.com/geoip/geolite2-free-geolocation-data
# ---------------------------------------------------------------------------

[provider.maxmind]
location = "local"
type     = "ip"
enabled  = false

[[provider.maxmind.category]]
name    = "Country"
mapping = ["geoip"]
source  = ["./GeoLite2-Country_*.tar.gz"]

[[provider.maxmind.category]]
name    = "ASN"
enabled = false
mapping = ["geoip"]
source  = ["./GeoLite2-ASN_*.tar.gz"]

[[provider.maxmind.category]]
name    = "City"
enabled = false
mapping = ["geoip"]
source  = ["./GeoLite2-City_*.tar.gz"]

# ---------------------------------------------------------------------------

# System hosts file — you might want to enable category for your OS.

[provider.system-hosts]
name     = "hosts"
location = "local"
type     = "domain"
enabled  = false

[[provider.system-hosts.category]]
name    = "unix"
tier    = 99
mapping = ["local"]
source  = ["/etc/hosts"]

[[provider.system-hosts.category]]
name    = "windows"
tier    = 99
enabled = false
mapping = ["local"]
source  = ["C:\\\\Windows\\\\System32\\\\drivers\\\\etc\\\\hosts"]

# ---------------------------------------------------------------------------
# S T A N D A R D S - normally you do not need to configure below
# ---------------------------------------------------------------------------

[provider.ip]
location = "inline"
type     = "ip"
enabled  = true

[[provider.ip.category]]
name    = "rfc1918"
mapping = ["local"]
source  = [
  "10.0.0.0/8",
  "172.16.0.0/12",
  "192.168.0.0/16",
]

[[provider.ip.category]]
name    = "loopback"
mapping = ["local"]
source  = [
  "127.0.0.0/8",
  "::1/128",
]

[[provider.ip.category]]
name    = "link-local"
tier    = 99
mapping = ["infrastructure"]
source  = [
  "169.254.0.0/16",
  "fe80::/10",
]

[[provider.ip.category]]
name    = "multicast"
tier    = 99
mapping = ["infrastructure"]
source  = [
  "224.0.0.0/4",
  "ff00::/8",
]

[[provider.ip.category]]
name    = "broadcast"
tier    = 99
mapping = ["infrastructure"]
source  = [
  "255.255.255.255/32",
]

[[provider.ip.category]]
name    = "cgNAT"
tier    = 99
mapping = ["infrastructure"]
source  = [
  "100.64.0.0/10",
]

[[provider.ip.category]]
name    = "pubDNS"
tier    = 99
mapping = ["infrastructure"]
source  = [
  "1.1.1.1",          # Cloudflare
  "8.8.8.8",          # Google
  "9.9.9.9",          # Quad9
  "208.67.222.222",   # OpenDNS
]

# ---------------------------------------------------------------------------
# Inline Domain Provider 'webstandard' - S T A N D A R D S
# ---------------------------------------------------------------------------

[provider.web]
location = "inline"
type     = "domain"
enabled  = true

[[provider.web.category]]
name    = "semantic"
tier    = 99
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

[[provider.web.category]]
name    = "bodies"
tier    = 99
mapping = ["infrastructure"]
source  = [
  "iana.org",
  "mozilla.org",
  "whatwg.org",
]

# ---------------------------------------------------------------------------
# Inline Domain Provider — loopback hostnames
# ---------------------------------------------------------------------------

[provider.loopback]
location = "inline"
type     = "domain"
enabled  = true

[[provider.loopback.category]]
name    = "Loopback hostnames"
tier    = 99
mapping = ["local"]
source  = [
  "localhost",
  "localhost.localdomain",
  "ip6-localhost",
  "ip6-loopback",
]

"""

def _strip_provider_sources(provider_cfg: dict) -> dict:
  """Return a copy of provider config with non-essential source lists removed.

  inline, local, and remote sources are only needed during cache build.
  DNS sources (resolver IPs) and sinkholes are kept — needed for live DNS lookup.
  The stripped version is merged into the main config dict as config["provider"].

  Args:
    provider_cfg: Full parsed provider.toml dictionary.

  Returns:
    Provider dict with non-dns sources removed from each category.
  """
  import copy
  stripped = copy.deepcopy(provider_cfg)
  for p in stripped.get("provider", {}).values():
    location = p.get("location")
    for cat in p.get("category", []):
      if location != "dns":
        cat.pop("source", None)  # inline/local/remote: in DB, not needed at runtime
      # dns: keep source (resolver IPs) and sinkhole for live lookup

  # keep dns-resolve-filter and resolve at top level for runtime use
  for key in ("dns-resolve-filter", "resolve"):
    if key in provider_cfg:
      stripped[key] = copy.deepcopy(provider_cfg[key])

  return stripped

def load_provider_config(main_config_path: Path, config: dict) -> dict | None:
  """Load provider.toml, merge stripped version into config, return full config for cache.

  Reads `meta.use-provider` from config. If false, sets config["provider"] = False
  and returns None. If true, loads provider.toml, validates it, merges a source-stripped
  version into config["provider"], and returns the full provider config for build_cache().

  Args:
    main_config_path: Path to the active altbrow.toml file.
    config: Parsed altbrow config dictionary — modified in place with ["provider"] key.

  Returns:
    Full parsed provider config dict (with sources) for build_cache(), or None if disabled.

  Raises:
    ConfigError: If use-provider is true but provider.toml does not exist or is invalid.
  """
  meta = config.get("meta", {})
  use_provider = meta.get("use-provider", False)

  if not use_provider:
    config["provider"] = False
    return None

  provider_path = main_config_path.parent / "provider.toml"

  if not provider_path.exists():
    raise ConfigError(f"Provider config not found: {provider_path}")

  provider_cfg = load_toml(provider_path)
  validate_provider_config(provider_cfg)

  # merge provider and dns-resolve-filter into main config
  # do NOT merge meta — provider.toml meta would overwrite altbrow.toml meta
  stripped = _strip_provider_sources(provider_cfg)
  MERGE_KEYS = {"provider", "dns-resolve-filter", "resolve"}
  for key, value in stripped.items():
    if key in MERGE_KEYS:
      config[key] = value

  return provider_cfg

def _build_cache_text(cache_path: Path | None, current_pv: str | None = None) -> str:
  """Return a one-line cache metadata summary for --validate-config."""
  if cache_path is None or not cache_path.exists():
    return "Cache: not found."
  import sqlite3
  size_label = format_size(cache_path.stat().st_size)
  try:
    con = sqlite3.connect(cache_path)
    def _meta(key: str) -> str | None:
      row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
      return row[0] if row else None
    built_at     = (_meta("built_at") or "")[:10] or "unknown"
    domain_count = _meta("domain_count")
    ip_count     = _meta("ip_count")
    cache_pv     = _meta("provider_config_version")
    con.close()
  except Exception:
    return f"Cache: {size_label}, metadata unavailable."
  if cache_pv:
    pv_part = f"provider v{cache_pv}"
    if current_pv and current_pv != cache_pv:
      pv_part += f" (current: v{current_pv})"
  else:
    pv_part = None
  if domain_count is not None and ip_count is not None:
    counts_part = f"{int(domain_count):,} domains, {int(ip_count):,} IPs"
  else:
    counts_part = "rebuild cache for counts"
  parts = [f"Cache: {size_label}", f"built {built_at}"]
  if pv_part:
    parts.append(pv_part)
  parts.append(counts_part)
  return ", ".join(parts) + "."

def validate_altbrow_config(
  config: dict,
  cache_path: Path | None = None,
  provider_config_version: str | None = None,
  config_path: Path | None = None,
) -> str:
  """Validate an altbrow config dictionary and return a human-readable summary.

  Checks all required sections (`[meta]`, `[client]`, `[client.profiles]`) and
  optional sections (`[validation]`, `[output]`). Provider summary is read from
  config["provider"] which is set by load_provider_config().

  Args:
    config: Merged altbrow config dict — must have been processed by
      load_provider_config() so config["provider"] is set.
    cache_path: Path to the SQLite cache file (optional).
    provider_config_version: Version string from provider.toml meta (optional).
    config_path: Path to the active altbrow.toml — shown in output (optional).

  Returns:
    Multi-line string summarizing the active configuration.

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
  use_provider = meta.get("use-provider", False)
  if not isinstance(use_provider, bool):
    raise ConfigError("meta.use-provider must be boolean")

  provider_data = config.get("provider", False)
  if use_provider and provider_data:
    dns_rf = config.get("dns-resolve-filter", {})
    resolve_cfg = config.get("resolve", {})
    provider_text = summarize_provider({"provider": provider_data, "dns-resolve-filter": dns_rf, "resolve": resolve_cfg})
  elif use_provider and not provider_data:
    provider_text = "Provider configuration enabled but not loaded."
  else:
    provider_text = "Provider configuration disabled."

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

  cache_text = _build_cache_text(cache_path, current_pv=provider_config_version)

  # --- description sentence ---
  lines = [
    f"Altbrow Version v{__version__} reads with config Version {config_version} from {config_date}"
    + (f",\nread from {config_path.resolve()}." if config_path else "."),
    f"It operates {activity} {consented} and counts domains, cookies, html, jsonld and microdata.",
    f"Default structured output format is {output_text}.",
    f"It {'does' if 'microdata_vs_jsonld' in validation else 'does not'} analyse microdata vs jsonld comparison for the summary.",
    "---",
    provider_text,
    "---",
    cache_text,
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

  # count non-dns categories validated by dns-resolve-filter
  # without filter: all enabled non-dns categories are validated
  # with filter: only those matching tier/category criteria
  dns_filter = provider_cfg.get("dns-resolve-filter", {})
  from .dns_lookup import _should_query_category
  validated   = 0
  for p in providers.values():
    if p.get("location") == "dns":
      continue
    if not p.get("enabled", False):
      continue
    for cat in p.get("category", []):
      if not cat.get("enabled", True):
        continue
      if _should_query_category(cat, dns_filter):
        validated += 1

  if loc_counts.get("dns", 0) > 0:
    if dns_filter:
      dns_str = f"\n                 {validated} of {ccount} categories are validated additional by dns-resolve-filter"
    else:
      dns_str = f"\n                 {ccount} categories are validated by dns-resolve-filter"
  else:
    dns_str = ""

  # geoip provider info
  geo_names = [
    cat.get("name") for p in providers.values()
    if isinstance(p, dict) and p.get("enabled") and p.get("location") not in ("dns",)
    for cat in p.get("category", [])
    if cat.get("enabled", True) and "geoip" in cat.get("mapping", []) and cat.get("name")
  ]
  if geo_names:
    geo_str = f"\n                 geoIP classification activated for {", ".join(geo_names)}"
  else:
    geo_str = "\n                 no geoIP provider activated"

  # domain resolve status
  resolve = provider_cfg.get("resolve", {})
  resolve_enabled = resolve.get("resolve-domains", RESOLVE_DEFAULTS["resolve-domains"])
  resolve_str = ", domain lookup enabled" if resolve_enabled else ", domain lookup disabled"

  return (
    f"Provider config: {pcount}{loc_str} of total {pcount_sum} provider active "
    f"with {ccount} of total {ccount_sum} categories enabled."
    f"{dns_str}"
    f"{geo_str}{resolve_str}"
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

  # --- resolve (optional, defaults from RESOLVE_DEFAULTS) ---
  resolve = cfg.get("resolve", {})
  if resolve:
    rd = resolve.get("resolve-domains")
    if rd is not None and not isinstance(rd, bool):
      raise ConfigError("resolve.resolve-domains must be boolean")
    resolver = resolve.get("resolver")
    if resolver is not None:
      if not isinstance(resolver, list) or not resolver:
        raise ConfigError("resolve.resolver must be a non-empty list")
      for r in resolver:
        if not isinstance(r, str):
          raise ConfigError("resolve.resolver entries must be strings")
        if r != "os" and not any(c.isdigit() for c in r):
          raise ConfigError(f"resolve.resolver invalid entry '{r}' (use \"os\" or IP address)")
    timeout = resolve.get("resolver-timeout")
    if timeout is not None:
      if not isinstance(timeout, int) or timeout <= 0:
        raise ConfigError("resolve.resolver-timeout must be a positive integer (seconds)")

  # --- dns-resolve-filter (optional) ---
  dns_filter = cfg.get("dns-resolve-filter", {})
  if dns_filter:
    cats = dns_filter.get("enabled-categories")
    if cats is not None:
      if not isinstance(cats, list):
        raise ConfigError("dns-resolve-filter.enabled-categories must be a list")
      for c in cats:
        if c not in ALLOWED_MAPPINGS:
          raise ConfigError(f"dns-resolve-filter.enabled-categories invalid: '{c}'")
    max_tier = dns_filter.get("max-tier")
    if max_tier is not None:
      if not isinstance(max_tier, int) or max_tier < 0:
        raise ConfigError("dns-resolve-filter.max-tier must be a non-negative integer")
    filter_mode = dns_filter.get("filter-mode")
    if filter_mode is not None and filter_mode not in ("or", "and"):
      raise ConfigError("dns-resolve-filter.filter-mode must be \"or\" or \"and\"")

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

    # --- dns: sinkhole per category, resolver IPs in category source ---

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
          raise ConfigError(f"{cname} tier must be a non-negative integer (0 = highest priority)")

      # --- mapping ---
      if "mapping" not in c:
        raise ConfigError(f"{cname} missing 'mapping'")

      mapping = _as_list(c["mapping"])

      for m in mapping:
        if m not in ALLOWED_MAPPINGS:
          raise ConfigError(f"{cname} invalid mapping '{m}'")

      # --- sinkhole: required per dns category ---
      if location == "dns":
        if "sinkhole" not in c:
          raise ConfigError(f"{cname} missing 'sinkhole' (required for dns categories)")
        sinkholes = c["sinkhole"]
        if not isinstance(sinkholes, list) or len(sinkholes) == 0:
          raise ConfigError(f"{cname} sinkhole must be a non-empty list")
        for s in sinkholes:
          if not isinstance(s, str):
            raise ConfigError(f"{cname} sinkhole entries must be strings")

      # --- source: resolver IPs for dns, file/url/domain for others ---
      if "source" not in c:
        raise ConfigError(f"{cname} missing 'source'")

      sources = c["source"]

      if not isinstance(sources, list) or len(sources) == 0:
        raise ConfigError(f"{cname}.source must be a non-empty list")

      if location == "dns":
        # source = resolver IP addresses
        for src in sources:
          if not isinstance(src, str):
            raise ConfigError(f"{cname} dns source entries must be strings (resolver IPs)")
        continue

      is_geoip = "geoip" in mapping

      for src in sources:

        if not isinstance(src, str):
          raise ConfigError(f"{cname}.source entries must be strings")

        if location == "remote":
          if not (src.startswith("http://") or src.startswith("https://")):
            raise ConfigError(f"{cname} remote source must be URL")
          if is_geoip and not src.endswith(".tar.gz"):
            raise ConfigError(f"{cname} geoip remote source must be a .tar.gz URL")

        elif location == "local":
          if src.startswith("http://") or src.startswith("https://"):
            raise ConfigError(f"{cname} local source must be file path or glob")
          if is_geoip:
            # glob patterns allowed for geoip local sources
            if not (src.endswith(".tar.gz") or src.endswith(".mmdb") or "*" in src or "?" in src):
              raise ConfigError(f"{cname} geoip local source must be .tar.gz, .mmdb or glob pattern")

        elif location == "inline":
          if ptype == "domain":
            if "." not in src and src not in ALLOWED_LOCAL_HOSTNAMES:
              raise ConfigError(f"{cname} invalid domain '{src}'")

          elif ptype == "ip":
            if not any(ch.isdigit() for ch in src):
              raise ConfigError(f"{cname} invalid ip/cidr '{src}'")

    if p["enabled"] and enabled_category_count == 0:
      raise ConfigError(f"Provider '{pname}' enabled but no category is enabled")