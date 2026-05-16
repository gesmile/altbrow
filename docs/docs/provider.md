# Provider System

The provider system is the central classification engine of altbrow.
It maps domains and IP addresses to semantic categories (ads, tracking, malware, etc.)
using a configurable, multi-source lookup pipeline.

Providers are defined and switched on in `provider.toml`, the whole subsystem is activated via `use-provider = true` in `altbrow.toml`.

---

## Concepts

### Provider

A named block in `provider.toml` that defines one classification source.
Each provider has a `location` (where to find the data), a `type` (what it classifies),
and one or more `category` entries.

### Category

A sub-list within a provider that maps a specific source to one or more altbrow categories.
A provider can have multiple categories — for example, one IP list for `malware` and another for `suspicious`.

### Tier

Controls match priority when multiple providers match the same domain or IP.
Lower tier wins. Tier 0 is the highest possible priority.
Inline and local providers default to tier 1; DNS and remote to tier 2.
Any non-negative integer is valid — freely assignable.

---

## Provider Schema

```toml
[provider.<name>]
name            = "Human readable label"   # optional
location        = "inline|local|remote|dns"
type            = "ip|domain"
enabled         = true                     # optional, default: true
subdomain_match = true                     # optional, default: true
                                           # true:  cdn.example.com matches if example.com is listed
                                           # false: exact hostname match only (recommended for large lists)

[[provider.<name>.category]]
name     = "Human readable label"          # optional
enabled  = true                            # optional, default: true
tier     = 1                               # optional, default: by location (see Tier)
mapping  = ["<category>"]                  # one or more altbrow categories
source   = ["..."]                         # depends on location type (see below)
sinkhole = ["<ip>", ...]                   # dns only: sinkhole IPs for this category
```

---

## Location Types

### `inline`

Entries defined directly in `provider.toml`. No file or network access at runtime.

```toml
[provider.cdn]
location = "inline"
type     = "domain"
enabled  = true

[[provider.cdn.category]]
name    = "Major CDNs"
mapping = ["cdn"]
source  = ["cloudfront.net", "akamai.net", "fastly.net"]
```

For `type = "ip"`:

```toml
[[provider.blocklist.category]]
mapping = ["suspicious"]
source  = ["1.2.3.4", "10.0.0.0/8"]
```

---

### `local`

Reads from files on the local filesystem. Paths are relative to `provider.toml`.
Glob patterns are supported (`*`, `?`).

See [File Formats](#file-formats) for supported source file types.

```toml
[provider.fail2ban]
location = "local"
type     = "ip"
enabled  = true

[[provider.fail2ban.category]]
mapping = ["suspicious"]
source  = ["./fail2ban.txt"]
```

```toml
[provider.system-hosts]
location = "local"
type     = "domain"
enabled  = true

[[provider.system-hosts.category]]
tier    = 99
mapping = ["local"]
source  = ["/etc/hosts"]
```

---

### `remote`

Downloads source lists from URLs over HTTP/HTTPS. Lists are cached locally via `--build-cache`.
Only `https://` and `http://` URLs are accepted.

```toml
[provider.ipfire]
location = "remote"
type     = "domain"
enabled  = true

[[provider.ipfire.category]]
name    = "Malware"
tier    = 1
mapping = ["malware"]
source  = ["https://dbl.ipfire.org/lists/malware/domains.txt"]

[[provider.ipfire.category]]
name    = "Advertising"
enabled = false
tier    = 9
mapping = ["ads"]
source  = ["https://dbl.ipfire.org/lists/ads/domains.txt"]
```

---

### `dns`

Sends live DNS queries to a configured resolver and checks whether the returned IP
matches a known sinkhole address. If it does, the domain is classified accordingly.

`source` contains the resolver IP addresses for this category.
`sinkhole` contains the IPs the resolver returns for blocked domains.

```toml
[provider.pihole]
location = "dns"
type     = "domain"
enabled  = true

[[provider.pihole.category]]
name     = "Ads (PiHole)"
mapping  = ["ads"]
source   = ["192.168.1.1"]
sinkhole = ["0.0.0.0", "::", "::ffff:0.0.0.0"]
```

```toml
[provider.opendns]
name     = "OpenDNS"
location = "dns"
type     = "domain"
enabled  = true

[[provider.opendns.category]]
name     = "Malware/Phishing"
mapping  = ["malware"]
source   = ["208.67.222.222", "208.67.220.220"]
sinkhole = ["146.112.61.104", "146.112.61.105"]
```

DNS providers are always queried for all enabled categories.
Use `dns-resolve-filter` to restrict which cache-matched entries are also DNS-verified.

---

## GeoIP Provider

GeoIP is modeled as a standard provider with `mapping = ["geoip"]`.
It uses MaxMind GeoLite2 databases in `.tar.gz` or `.mmdb` format.
Glob patterns are supported for local sources to resolve the latest downloaded archive.

```toml
[provider.maxmind]
location = "local"
type     = "ip"
enabled  = true

[[provider.maxmind.category]]
name    = "Country"
mapping = ["geoip"]
source  = ["./GeoLite2-Country_*.tar.gz"]

[[provider.maxmind.category]]
name    = "ASN"
enabled = false
mapping = ["geoip"]
source  = ["./GeoLite2-ASN_*.tar.gz"]
```

GeoIP data is included automatically in JSON/YAML output when enabled.
The summary line shows country distribution counts.

Download: [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data)

---

## Categories (Mappings)

There are 12 categories in `ALLOWED_MAPPINGS`. 10 are user-assignable via `mapping = [...]`
in `provider.toml`; 2 are internal and cannot be set by providers.

### User-assignable categories (10)

These can be used freely as `mapping` values in any provider category.
`local` and `infrastructure` can also be triggered automatically by built-in detection
(RFC1918 ranges, multicast, link-local) — a provider mapping extends or overrides that.

| Category        | Group         | Description |
|-----------------|---------------|-------------|
| `ads`           | content       | Advertising networks and ad delivery |
| `analytics`     | content       | User behaviour measurement and reporting |
| `cdn`           | content       | Content delivery networks and static asset hosting |
| `malware`       | content       | Malware, phishing, known hostile domains or IPs |
| `social`        | content       | Social networks, dating, gambling, adult content |
| `suspicious`    | content       | Unverified or potentially hostile |
| `telemetry`     | content       | Error reporting, performance monitoring, device telemetry |
| `tracking`      | content       | Cross-site user tracking and profiling |
| `local`         | special       | RFC1918, localhost, loopback, your own domains |
| `infrastructure`| special       | Multicast, link-local, broadcast, technical protocol addresses |

### Internal categories (2)

These are assigned by altbrow automatically and cannot be used as `mapping` values.

| Category  | Description |
|-----------|-------------|
| `unknown` | Default when no provider matched — assigned automatically |
| `geoip`   | Provider type marker for GeoIP databases — not a classification result |

### Automatic relation categories (derived, no provider needed)

These describe the structural relation of a domain to the analysed URL, not a provider classification.

| Category       | Description |
|----------------|-------------|
| `FIRST_PARTY`  | Same registrable domain as the analysed page |
| `PEER`         | Sibling subdomain (e.g. `images.example.com`) |
| `SUBDOMAIN`    | Subdomain of the analysed host |
| `EXTERNAL`     | Different registrable domain |

---

## Resolve Configuration

Controls domain-to-IP resolution. Defined in `provider.toml` under `[resolve]`.

```toml
[resolve]
resolve-domains  = false       # resolve domains to IP, check against IP provider lists
resolver         = ["os"]      # "os" = system resolver, or IP: ["1.1.1.1", "8.8.8.8"]
resolver-timeout = 2           # seconds per DNS query
```

| Key                | Default  | Description |
|--------------------|----------|-------------|
| `resolve-domains`  | `false`  | Enable domain→IP resolution |
| `resolver`         | `["os"]` | DNS resolver(s) to use |
| `resolver-timeout` | `2`      | Timeout in seconds |

---

## DNS Resolve Filter

Controls which cache-matched entries also trigger a live DNS verification query.
This is distinct from which DNS providers are queried — all enabled DNS providers
are always queried unconditionally.

```toml
[dns-resolve-filter]
enabled-categories = ["malware", "suspicious"]
max-tier           = 1
filter-mode        = "and"
```

| Key                  | Description |
|----------------------|-------------|
| `enabled-categories` | Only entries matching these categories trigger DNS verification |
| `max-tier`           | Only entries with tier ≤ this value trigger DNS verification |
| `filter-mode`        | `"or"`: category match **or** tier match; `"and"`: both required |

**Examples:**

```toml
# Verify only high-priority malware/suspicious entries (tier 1):
[dns-resolve-filter]
enabled-categories = ["malware", "suspicious"]
max-tier           = 1
filter-mode        = "and"

# Verify anything classified as malware, regardless of tier:
[dns-resolve-filter]
enabled-categories = ["malware"]
filter-mode        = "or"

# Disable all DNS verification (without disabling DNS providers):
[dns-resolve-filter]
enabled-categories = []
filter-mode        = "and"
```

If `[dns-resolve-filter]` is absent, all enabled non-DNS categories trigger DNS verification.

---

## Lookup Flow

```
Domain / IP
    │
    ├─► Relation derivation (FIRST_PARTY, PEER, SUBDOMAIN, EXTERNAL) — no provider needed
    │
    └─► lookup_domain() / lookup_ip()
            │
            ├─ SQLite cache lookup
            │       ├─ Hit  → return matching categories
            │       └─ Miss → (no categories from cache)
            │
            └─ DNS providers (live, parallel — if any DNS provider enabled)
                    │
                    ├─ dns-resolve-filter absent → query ALL domains (hits and misses)
                    │
                    └─ dns-resolve-filter set   → query only if a cache hit matches the filter
                                                   cache miss + active filter → DNS skipped
                                                   → result stays unknown
```

**Notes:**
- `local` and `infrastructure` are regular provider categories, not built-in detection.
  They must be configured as provider entries (inline or local) in `provider.toml`.
- DNS providers are always queried unconditionally once `should_query_dns` is true.
- Cache is built with `altbrow --build-cache`. Remote sources are downloaded,
  local and inline sources are indexed, GeoIP archives are extracted.

---

## Provider Priority (Tier)

When multiple providers match the same entry, the one with the lowest tier wins.
Tier system works with provider and categories.
On a tie, the first match in the SQLite cache is used.

| Tier | Meaning |
|------|---------|
| 0    | Highest priority — wins over all other tiers |
| 1    | Default for `inline` and `local` providers |
| 2    | Default for `dns` and `remote` providers |
| 0–n  | Any non-negative integer; freely assignable |


Override per category:

```toml
[[provider.ipfire.category]]
name    = "Malware"
tier    = 1          # higher priority than default remote tier
mapping = ["malware"]
source  = ["https://dbl.ipfire.org/lists/malware/domains.txt"]
```

---

## File Formats

All `local` and `remote` sources use the same parser (`parse_entries()`).
Format is auto-detected per file — no configuration needed.

### Plain list

One domain, IP, or CIDR per line. Lines starting with `#` are ignored.

```
# comment
example.com
tracker.io
1.2.3.4
10.0.0.0/8
```

### Hosts file

Standard `/etc/hosts` format. The sinkhole IP (`0.0.0.0`, `127.0.0.1`, `::`) in the
first column is stripped — only the hostname is used. Inline comments after `#` are ignored.

```
0.0.0.0   ads.example.com   # blocked
127.0.0.1 tracker.io
```

Compatible with StevenBlack hosts, Pi-hole export, and system `/etc/hosts`.

### CSV / TSV

Delimiter auto-detected from the first data line in priority order: TAB → SPACE → `;` → `,`.
Quoted fields (`"example.com"`, `'example.com'`) are unquoted automatically.

Two layouts are supported:

**Domain/IP first column** — entry is taken from column 1, rest ignored:

```
example.com,Title,Description
tracker.io,"Ad Network",2024
```

**URL first column** — hostname is extracted from the URL, rest ignored:

```
https://www.example.com	Page Title	Category
https://tracker.io	Tracker	Ads
```

Used by Curlie (`rdf-*-c.tsv`) and Tranco (`top-1m.csv`).

### ABP (AdBlock Plus)

Domain-only filter rules in `||domain^` or `||domain.` syntax.
Lines starting with `!` (comments) or `[` (section headers like `[Adblock Plus 2.0]`) are ignored.
Script rules, element selectors, and other non-domain rules are skipped automatically.

```
[Adblock Plus 2.0]
! Title: My blocklist
||ads.example.com^
||tracker.io^
```

No configuration needed — ABP format is auto-detected when the first data line starts with `||`.

### Bookmarks HTML (`NETSCAPE-Bookmark-file-1`)

Browser bookmark exports from Firefox, Chrome, Edge, and Safari.
All `<A HREF="...">` links are parsed; only `http://` and `https://` URLs are used.
The hostname is extracted from each URL — duplicates are removed.

Triggered automatically when the source file has a `.html` extension.

```toml
[[provider.bookmarks.category]]
mapping = ["local"]
source  = ["./bookmarks.html"]
```
