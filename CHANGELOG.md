# Release Notes


v0.1.1-rc3: integration tests, provider system improvements

- CI pipeline: build/validate/integration jobs, mock server
- IP classification fix: IPs in HTML URLs now correctly routed to classify_ip()
- Glob support for local provider sources (provider.d/*.txt)
- Hosts-format parsing for local domain lists
- GeoIP: tar.gz extraction fix, warning cleanup
- fetch_remote: meta injection removed (security)
- extract.py: IP/domain split in URL host processing
- Test data: test.html with JSON-LD/Microdata pairs for validator
