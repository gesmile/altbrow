# Release Notes

v0.1.1-rc4: provider import improvements, transport metadata

- refactor: result output keys renamed for consistent JSON output filtering
- feat: `transport` top-level key in result array — HTTP version, redirect chain, TLS protocol/cipher/pki, HTTP response headers
  - captured from the already-open socket (no extra network call)
  - text output: `Connection` line in summary; `=== Transport ===` section at `-v`; redirects and HTTP response headers shown at `-vv`
  - JSON/YAML output: full `transport` dict including `http.headers` included automatically
  - `tls` is `null` for plain HTTP connections
- feat: extend provider system
  - ABP filter format support: auto-detects `||domain^` and `||domain.` syntax; ignores `!` comments, `[Section]` headers, URL rules, and entries without a valid TLD
  - skip counter logged at INFO level for all import formats
  - `.html` files are treated as browser bookmark exports (`<!DOCTYPE NETSCAPE-Bookmark-file-1>`); depending on `provider.type` domains and IPs are extracted automatically
  - universal line parser: auto-detects delimiter (tab, space, semicolon, comma) from the first data line; handles quoted fields, strips inline comments, and deduplicates per file; URL-first lines (TSV/CSV format) are detected and parsed
  - add examples to generated default `provider.toml`
- feat: add project logos and repository-open-graph image
- perf: domains/ips tables redesigned, new provider_categories table -> existing `.altbrow.cache` must be rebuilt
- perf: text output refinements: placeholders removed, empty sections suppressed, connection summary added
- fix: `dns-resolve-filter` is now a runtime gate; without a filter, all domains are queried unconditionally (previous behavior)
- test: URL-first lines, Curlie TSV, bookmarks HTML via cache, oisd-small provider (ABP format); `xfail` documented for mixed plain+hosts edge case
- test: integration tests assert `transport` key, `http.version`, `http.redirects`, and `tls: null` for HTTP


v0.1.1-rc3: integration tests, provider system improvements

- CI pipeline: build/validate/integration jobs, mock server
- IP classification fix: IPs in HTML URLs now correctly routed to classify_ip()
- Glob support for local provider sources (provider.d/*.txt)
- Hosts-format parsing for local domain lists
- GeoIP: tar.gz extraction fix, warning cleanup
- fetch_remote: meta injection removed (security)
- extract.py: IP/domain split in URL host processing
- Test data: test.html with JSON-LD/Microdata pairs for validator
