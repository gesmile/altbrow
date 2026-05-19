# Result data structure

Altbrow analyses a webpage and presents the result as a JSON structure for downstream processing.   
Pipe the output directly through [jq](https://jqlang.org/ "lightweight and flexible command-line JSON processor") or save it to a file for later use.

The data structure follows the natural layers of a web document:

>  transport, signals, embedded data, and HTML content.

See [jq Examples](jq-examples.md) for filtering and processing recipes.

## Existing data structure

```

{
  "transport": {
    "http": {
      "version": 
      "headers": [],
      "redirects": []
    },
    "tls": {
      "protocol":
      "cipher":
      "pki":
    }
  },
  "data": {
    "jsonld": [],
    "micro": []
  },
  "signals": {
    "domains": [
      {
        "value": 
        "apex":
        "rel":
        "cat":
        "categories": [],
        "occ": [],
        "ip": {
          "addr": 
          "geo": {
            "country":,
            "asn":,
            "org":
          }
        }
      }
    ],
    "ips": [],
    "cookies": []
  }
}

```

## Planned data structure

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
