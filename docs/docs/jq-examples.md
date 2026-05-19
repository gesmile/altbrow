# jq Examples

Practical examples for filtering and transforming altbrow JSON output with
[jq](https://jqlang.org/ "lightweight and flexible command-line JSON processor").

See [Result Structure](result-structure.md) for the full field reference.

---

## Snippets

```bash
# category, country and occurrence per domain
altbrow -f json <URL> | jq -c '.signals.domains[] | {domain: .value, cat, country: .ip.geo.country, occ}'

# all provider hits per domain
altbrow -f json <URL> | jq -c '.signals.domains[] | {domain: .value, cats: [.categories[] | "\(.provider):\(.name)"] | join(", ")} + .occ'

# unique categories per domain
altbrow -f json <URL> | jq -c '.signals.domains[] | {domain: .value, cat, cats: [.categories[].category] | unique, occ: .occ}'

# external domains only
altbrow -f json <URL> | jq -c '.signals.domains[] | select(.rel == "EXTERNAL") | {domain: .value, cat, country: .ip.geo.country}'

# domains per provider
altbrow -f json <URL> | jq -c '.signals.domains[] | . as $d | .categories[] | {domain: $d.value, cat: .category, provider, tier}'
```

---

## Filtered output — example.com

Results vary depending on your provider configuration.

### unique categories per domain

```bash
altbrow -f json example.com | jq -c '.signals.domains[] | {domain: .value, cat, cats: [.categories[].category] | unique, occ: .occ}'
```

```json
{"domain":"example.com","cat":"ads","cats":["ads","social","tracking"],"occ":{"target":1}}
{"domain":"iana.org","cat":"social","cats":["infrastructure","social"],"occ":{"link":1}}
```

### all provider hits per domain

```bash
# occ keys are merged to top level via + .occ
altbrow -f json example.com | jq -c '.signals.domains[] | {domain: .value, cats: [.categories[] | "\(.provider):\(.name)"] | join(", ")} + .occ'
```

```json
{"domain":"example.com","cats":"stevenblack:Ads and Malware, hagezi:pro, majestic:1M","target":1}
{"domain":"iana.org","cats":"majestic:1M, web:bodies","link":1}
```

---

## Full output — example.com

```
altbrow -f json example.com
```

```json
{
  "transport": {
    "http": {
      "version": "HTTP/1.1",
      "headers": {
        "Date": "Tue, 19 May 2026 08:52:15 GMT",
        "Content-Type": "text/html",
        "Transfer-Encoding": "chunked",
        "Connection": "keep-alive",
        "Server": "cloudflare",
        "last-modified": "Thu, 14 May 2026 05:31:28 GMT",
        "allow": "GET, HEAD",
        "Age": "6448",
        "cf-cache-status": "HIT",
        "Content-Encoding": "gzip",
        "CF-RAY": "9fe1dd4c0f3ce0db-MUC"
      },
      "redirects": []
    },
    "tls": {
      "protocol": "TLS 1.3",
      "cipher": "TLS_AES_256_GCM_SHA384",
      "pki": "valid"
    }
  },
  "data": {
    "jsonld": [],
    "micro": []
  },
  "signals": {
    "domains": [
      {
        "value": "example.com",
        "apex": "example.com",
        "rel": "FIRST_PARTY",
        "cat": "ads",
        "categories": [
          {
            "category": "ads",
            "provider": "stevenblack",
            "location": "remote",
            "name": "Ads and Malware",
            "tier": 0
          },
          {
            "category": "tracking",
            "provider": "hagezi",
            "location": "remote",
            "name": "pro",
            "tier": 1
          },
          {
            "category": "social",
            "provider": "majestic",
            "location": "local",
            "name": "1M",
            "tier": 2
          }
        ],
        "occ": {
          "target": 1
        },
        "ip": {
          "addr": "172.66.147.243",
          "geo": {
            "country": "US",
            "asn": "AS13335",
            "org": "Cloudflare, Inc."
          }
        }
      },
      {
        "value": "iana.org",
        "apex": "iana.org",
        "rel": "EXTERNAL",
        "cat": "social",
        "categories": [
          {
            "category": "social",
            "provider": "majestic",
            "location": "local",
            "name": "1M",
            "tier": 0
          },
          {
            "category": "infrastructure",
            "provider": "web",
            "location": "inline",
            "name": "bodies",
            "tier": 1
          }
        ],
        "occ": {
          "link": 1
        },
        "ip": {
          "addr": "192.0.43.8",
          "geo": {
            "country": "US",
            "asn": "AS40528",
            "org": "ICANN"
          }
        }
      }
    ],
    "ips": [],
    "cookies": []
  }
}
```
