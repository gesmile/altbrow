# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**altbrow** is a Python CLI tool that acts as a crawler-like browser for deep analysis of websites — examining semantic structure, external dependencies, cookies, and structured data (JSON-LD, Microdata). Requires Python 3.12+.

- **Provider system**: `provider.toml` is the single source of truth for all providers
- **Config**: `altbrow.toml` for user config — never overwritten by provider merge
- **Cache**: `.altbrow.cache` (SQLite) placed adjacent to the active config file
- **GeoIP**: Standard provider (`type = "geoip"`), uses MaxMind GeoLite2 MMDB files
- **DNS**: All enabled DNS providers are always queried unconditionally when DNS runs
- `dns-resolve-filter` gates whether DNS runs at all: with a filter, DNS is only triggered for domains with a static cache hit matching the filter; without a filter every domain is queried
- `ALLOWED_MAPPINGS` in `config.py` is the canonical reference for provider mappings

## Commands

```bash
# Install for development
pip install -e .[dev]

# Lint and type-check
ruff check altbrow
ruff format .
mypy altbrow --ignore-missing-imports

# Run tests (unit)
pytest tests/test_import.py tests/test_resolve.py tests/test_provider_config.py tests/test_cli.py -v

# Run tests (cache)
pytest tests/test_cache.py -v

# Run integration tests (starts its own mock HTTP server)
pytest tests/test_integration.py -v

# Run a single test
pytest tests/test_foo.py::test_bar

# Build package
python -m build

# Pin dependencies
pip-compile pyproject.toml -o requirements.txt
pip-compile pyproject.toml --extra dev -o requirements-dev.txt

# CLI
altbrow <URL>
altbrow --validate-config
altbrow --build-cache
altbrow -V
```

Ruff uses 2-space indent (`indent-width = 2`, `line-length = 88`).

## Architecture

### Data flow

```
URL
 → fetch.py          — HTTP fetch, IRI normalization, redirects, cookie capture
 → extract.py        — HTML tag parsing (assets/links), structured data (extruct), cookie classification
 → classify_domain() — SQLite cache lookup + optional live DNS queries
 → classify_ip()     — CIDR-aware SQLite lookup + optional GeoIP enrichment
 → output.py         — text (summary/verbose) or JSON/YAML to stdout
```

### Key modules

| Module | Responsibility |
|---|---|
| `main.py` | CLI entry point (ArgumentParser), wires all modules together |
| `config.py` | TOML config discovery & validation; `ALLOWED_MAPPINGS`; generates defaults on first run |
| `fetch.py` | HTTP client; NFC-normalizes IRIs to percent-encoded URLs |
| `extract.py` | HTML tag extraction, extruct structured-data parsing, cookie extraction |
| `classify_cookies.py` | `classify_cookies()` — parses a raw `Set-Cookie` header, flags `third_party` and `cross_site` |
| `classify_domain.py` | Domain/IP relation + category classification against cache |
| `domain_utils.py` | `get_apex_domain()` — thin tldextract wrapper used across modules |
| `fetch_remote.py` | `parse_entries()` — shared parser for local and remote provider lists |
| `cache.py` | SQLite provider cache: build, schema, `lookup_domain()`, `lookup_ip()` |
| `dns_lookup.py` | Live parallel DNS queries via ThreadPoolExecutor, sinkhole detection |
| `geoip.py` | MaxMind GeoLite2 MMDB extraction and IP lookup; `GeoReaders` NamedTuple |
| `logging_config.py` | `setup_logging()` — configures root logger level and format |
| `output.py` | Multi-format rendering (text/JSON/YAML) |

### Configuration system

Two TOML files discovered in priority order:
1. `--config /path/to/altbrow.toml` (explicit)
2. `./altbrow.toml` (portable/development mode)
3. `~/.altbrow/altbrow.toml` (user mode, auto-generated on first run)

- **`altbrow.toml`** — client profile, output format, logging, feature flags
- **`provider.toml`** (or `altbrow-provider.toml`) — provider definitions; `[resolve]` section lives here, not in `altbrow.toml`
- **`.altbrow.cache`** — SQLite DB, lives next to `altbrow.toml`

Only these keys are merged from `provider.toml` into the main config:

```python
MERGE_KEYS = {"provider", "dns-resolve-filter", "resolve"}
```

### Provider system

Providers classify domains and IPs into categories (`ads`, `analytics`, `cdn`, `infrastructure`, `local`, `malware`, `social`, `suspicious`, `telemetry`, `tracking`, `unknown`, plus automatic `FIRST_PARTY`/`SUBDOMAIN`/`PEER`/`EXTERNAL` relations). `geoip` is a valid mapping value but marks a provider as a GeoIP enrichment source, not a classification category.

Provider locations: `inline`, `local`, `remote`, `dns`
Provider types: `domain`, `ip` (GeoIP providers are identified by `mapping = ["geoip"]`, not by a separate type)

**Tier-based winner selection**: multiple providers can match the same domain/IP; the entry with the lowest `tier` integer wins. Inline/local defaults to tier 1; remote/dns defaults to tier 2.

### Domain occurrence vs. relation

Two orthogonal classification axes on every signal:

- **Occurrence** (`TARGET`, `ASSET`, `LINK`, `MIXED`) — *where* the domain was found in the HTML
- **Relation** (`FIRST_PARTY`, `SUBDOMAIN`, `PEER`, `EXTERNAL`) — *structural position* relative to the analysed URL's apex domain (via tldextract)

### Cache schema

Two tables: `provider_categories` (~30 rows, one per provider+category combination) and `entries` (one row per domain/IP, integer FK to `provider_categories`). Indexed on `value` and `apex` (partial index, NULL for IPs/CIDRs). `meta` table stores `built_at` timestamp and `altbrow_version`. Multiple rows per domain are allowed (one per category match).

### Result data structure

Planned top-level shape of the analysis result (JSON/YAML export and internal `extracted` dict):

```
transport                     — connection layer (TLS, HTTP, redirects)
  tls                         — Peer information (target webserver)
    protocol                  — TLS 1.2 | TLS 1.3 (Protocol Version)
    cipher                    — e.g. TLS_AES_256_GCM_SHA384
    pki                       — overall chain status: valid | revoked | expired | untrusted | unknown
    certs[]                   — certificate chain (planned)
      subject
      issuer
      until                   — e.g. NotAfter: `Jun 25 15:32:05 2026 GMT`
      signature                — e.g. ecdsa_secp256r1_sha256
      trust                   — true|false (may use provider system or os)
      crl                     — passed|revoked|unknown (default)
  http
    version                   — HTTP/1.1 | HTTP/2 | HTTP/3
    headers                   — response headers (as dict)
    redirects[]               — redirect chain before final URL
      url                     — new URL
      status                  — HTTP status code

signals                       — external dependency signals
  domains[]
    value                     — hostname as seen in HTML
    apex                      — registrable domain (tldextract)
    rel                       — FIRST_PARTY | SUBDOMAIN | PEER | EXTERNAL
    cat                       — winning category (tier-based)
    categories[]              — all matched categories
      name                    — label from provider.toml
      category                — altbrow category
      provider                — provider name from provider.toml
      location                — inline | local | remote | dns
      tier                    — integer; 0 is highest priority
    occ                       — occurrence counts by context (dict, omitted keys = 0)
      target                  — analysed URL itself
      asset                   — img, script, link, iframe, …
      link                    — anchor <a href>
      cookie                  — Set-Cookie Domain= attribute
    ip                        — first resolved address (multi-homing ignored)
      addr                    — IP address string
      geo
        country               — ISO 3166-1 alpha-2
        city
        asn                   — e.g. AS197540
        org                   — organisation name
  ips[]                       — bare IPs found directly in HTML (not via domain resolution)
    value
    cat
    categories[]
    occ
    geo
      country
      city
      asn
      org
  cookies[]                   — Set-Cookie headers, parsed and classified (planned)

data                          — embedded structured data
  micro                       — Microdata
  jsonld                      — JSON-LD
  rdfa                        — RDFa (planned)

html                        — (planned soon)
  head
    title                   — <title> string
    base                    — <base href> if present
    meta[]                  — <meta name | property | http-equiv + content>
    link[]                  — <link rel=...> (canonical, stylesheet, icon,
                              preconnect, dns-prefetch, …)
    script[]                — <script> elements in head (inline + external)
    style[]                 — <style> inline CSS in head
    noscript[]              — <noscript> fallback content
  content[]                 — one entry per sectioning HTML5 element; body as
                              implicit root if none present (HTML4 compatibility)
    type                    — main | section | article | aside | header | nav | footer | body
    media[]                 — images, video, audio, iframes inside this section
    noscript[]              — <noscript> fallback content
    text
      structure[]           — h1–h6, p, dl/dt/dd, ol/ul/li, dfn, figure/figcaption
      special[]             — address, form, data, time
      emphasis[]            — blockquote, pre, em, strong, small, mark, cite,
                              code, q, abbr, kbd, samp, var, ins, del
  scripts[]                 — <script> elements in body (inline + external)
  css[]                     — <link rel=stylesheet> + <style> in body
  statistics                — (planned)
    bytes                   — bytes of HTML response
    media                   — total count of referenced media elements
    wc                      — word count of human-visible text
```

Notes:
- `data.*` (Microdata / JSON-LD / RDFa) and `web.structure.html.content` are parallel views
- `transport.tls.certs` is planned; implementation gated behind `--no-cert-check`
- `data.rdfa` is planned alongside the JSON-LD / Microdata / RDFa extraction milestone

## Key Decisions

- Timeouts in **seconds** throughout (not milliseconds); `test_resolve_defaults_values` asserts `== 2`, not `== 2000`
- Cache placement derived inline — no separate discovery function
- `geo` field included in `extracted` dict for JSON/YAML export
- GeoIP uses `mapping` field with MMDB filenames (consistent with provider model)
- Domain apex field named `apex` throughout (code, cache schema, JSON output)

## Coding Conventions

- **Indentation**: 2 spaces (Python)
- **Language**: English in all code, variable names, and comments
- **No silent renaming** of functions or variables without explicit instruction
- **Docstrings**: on all functions
- **Commits**: Conventional commits format (`feat:`, `fix:`, `chore:`, etc.)

## Exit codes

See [docs/exitcodes.md](docs/docs/exitcodes.md) for the full reference.

| Code | Meaning                    | Status          |
|------|----------------------------|-----------------|
| 0    | Success                    | implemented     |
| 1    | Unhandled exception        | Python OS default |
| 2    | CLI usage error            | implemented     |
| 3    | Config/cache error         | implemented     |
| 4    | Network/TLS/HTTP error     | implemented     |
| 5    | HTTP protocol error (4xx/5xx) | planned      |

## Open Items

- **`_paths`/`_runtime` refactor**: consolidate `cache_path`/`config_path`/`geo_readers` into `config["_paths"]` and `config["_runtime"]` so all functions take only `config` — detailed plan in `stack.md`
- mypy: 16 errors in 8 files (geoip, dns_lookup, extract, cache)
- DNS sequential-with-fallback strategy within a provider category's source list (pending)
- DNS provider integration test (mock DNS server)
- Pi-hole source IP visibility in DNS queries (pending investigation)
- `--client-profile consented` not yet implemented
