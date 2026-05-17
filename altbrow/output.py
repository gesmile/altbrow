# altbrow/output.py
#
#   render_output()
#   write_log()

import json
import logging
import sys

logger = logging.getLogger(__name__)

# ensure UTF-8 output on Windows (cp1252 default breaks unicode chars)
if hasattr(sys.stdout, "reconfigure"):
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
  import yaml
except ImportError:
  yaml = None


def _format_categories(cats: list[dict], providers: dict | None = None) -> str:
  """Format pre-sorted categories as a verbose provider list string.

  Categories must be pre-sorted by tier ascending (classify_domain does this).
  The winning category is read from the result dict's `cat` field — not derived here.
  providers is config["provider"] — used to resolve human-readable provider names.

  Returns:
    All categories as 'category(provider/name)' joined by ', ', or '-'.
  """
  if not cats:
    return "-"
  providers = providers or {}
  def _fmt(c: dict) -> str:
    p_label = providers.get(c["provider"], {}).get("name") or c["provider"]
    cat_label = c.get("name")
    label = f"{p_label}/{cat_label}" if cat_label else p_label
    return c["category"] + "(" + label + ")"
  return ", ".join(_fmt(c) for c in cats)


def _occ_str(occ: dict) -> str:
  """Format an occ count dict as an uppercase slash-joined string for text display."""
  return "/".join(k.upper() for k in occ) if occ else ""


def _connection_summary(transport: dict) -> str:
  """Build a one-line connection string for the summary section.

  Args:
    transport: transport dict from extracted result.

  Returns:
    Human-readable connection string, e.g.
    'HTTPS · HTTP/1.1 · TLS 1.3 (TLS_AES_256_GCM_SHA384)'
  """
  http = transport.get("http", {})
  tls  = transport.get("tls") or {}
  ver  = http.get("version") or "?"
  n_redir = len(http.get("redirects", []))

  n_headers = len(http.get("headers", {}))

  annot_parts = []
  if n_headers:
    annot_parts.append(f"h:{n_headers}")
  if n_redir:
    annot_parts.append(f"r:{n_redir}")
  annot   = f" ({', '.join(annot_parts)})" if annot_parts else ""
  ver_str = f"{ver}{annot}"

  if tls:
    proto  = tls.get("protocol", "")
    cipher = tls.get("cipher", "")
    pki    = tls.get("pki", "")
    s = f"HTTPS · {ver_str} · {proto} ({cipher})"
    if pki and pki != "valid":
      s += f" [pki: {pki}]"
  else:
    s = f"HTTP · {ver_str}"

  return s


def _render_transport(transport: dict, verbosity: int = 1) -> None:
  """Print the Transport section (verbosity >= 1) with redirect chain and optional headers.

  Args:
    transport: transport dict from extracted result.
    verbosity: 1 = protocol + redirects, 2 = additionally HTTP response headers.
  """
  http      = transport.get("http", {})
  redirects = http.get("redirects", [])

  print("\n=== Transport ===")
  print(f"  {_connection_summary(transport)}")
  if redirects:
    for r in redirects:
      print(f"    {r['status']}  {r['url']}")
  elif verbosity >= 2:
    print("  (no redirects)")

  if verbosity >= 2:
    headers = http.get("headers", {})
    if headers:
      print("  HTTP Response Headers")
      for k, v in headers.items():
        print(f"    {k}: {v}")


def _render_text(extracted: dict, verbosity: int, providers: dict | None = None) -> None:
  """Render human-readable text output to STDOUT.

  Args:
    extracted: Dict returned by extract_data().
    verbosity: Detail level (0=summary, 1=domains+ips, 2=full).
    providers: config["provider"] for human-readable label lookup.
    geo_readers: Open GeoReaders for live GeoIP lookup, or None.
  """
  transport  = extracted.get("transport", {})
  signals    = extracted.get("signals", {})
  structured = extracted.get("data", {})

  domains   = signals.get("domains", [])
  ips       = signals.get("ips", [])
  cookies   = signals.get("cookies", [])
  jsonld    = structured.get("jsonld", [])
  microdata = structured.get("micro", [])

  # count by winning category per domain (pre-computed cat field)
  cat_counts: dict[str, int] = {}
  for d in domains:
    winning = d.get("cat", "unknown")
    cat_counts[winning] = cat_counts.get(winning, 0) + 1

  cat_summary = ", ".join(
    f"{k}: {v}" for k, v in sorted(cat_counts.items())
  )

  # count by country code from structured ip.geo
  geo_counts: dict[str, int] = {}
  for d in domains:
    cc = d.get("ip", {}).get("geo", {}).get("country")
    if cc:
      geo_counts[cc] = geo_counts.get(cc, 0) + 1
  geo_summary = ", ".join(
    f"{k}: {v}" for k, v in sorted(geo_counts.items(), key=lambda x: -x[1])
  )

  # count by winning category per IP
  ip_cat_counts: dict[str, int] = {}
  for ip in ips:
    winning = ip.get("cat", "unknown")
    ip_cat_counts[winning] = ip_cat_counts.get(winning, 0) + 1

  ip_cat_summary = ", ".join(
    f"{k}: {v}" for k, v in sorted(ip_cat_counts.items())
  )

  print("\n=== Summary ===")
  print(f"Connection       : {_connection_summary(transport)}")
  geo_part = f" ({geo_summary})" if geo_summary else ""
  print(f"External domains : {len(domains)}" + (f" ({cat_summary})" if cat_summary else "") + geo_part)
  print(f"External IPs     : {len(ips)}" + (f" ({ip_cat_summary})" if ip_cat_summary else ""))
  print(f"Cookies          : {len(cookies)}")
  print(f"JSON-LD blocks   : {len(jsonld)}")
  print(f"Microdata blocks : {len(microdata)}")

  if verbosity < 1:
    return

  _render_transport(transport, verbosity)

  print("\n=== External Domains ===")
  from .geoip import format_geo as _fmt_geo
  for d in domains:
    winning = d.get("cat", "unknown")
    geo_str = _fmt_geo(d.get("ip", {}).get("geo", {}))
    geo_col = f"[{geo_str}]" if geo_str else "-"
    if verbosity >= 2:
      all_str = _format_categories(d.get("categories", []), providers)
      print(
        f"  {d['rel']:<12} {_occ_str(d.get('occ', {})):<10} "
        f"{d['value']:<40} {winning:<15} {geo_col:<20} {all_str}"
      )
    else:
      print(
        f"  {d['rel']:<12} {_occ_str(d.get('occ', {})):<10} "
        f"{d['value']:<40} {winning:<15} {geo_col}"
      )

  if ips or verbosity >= 2:
    print("\n=== External IPs ===")
  if ips:
    for ip in ips:
      winning = ip.get("cat", "unknown")
      occ_col = _occ_str(ip.get("occ", {}))
      geo_str = _fmt_geo(ip.get("geo", {}))
      geo_col = f"[{geo_str}]" if geo_str else "-"
      if verbosity >= 2:
        all_str = _format_categories(ip.get("categories", []), providers)
        print(
          f"  {ip['rel']:<12} {occ_col:<10} "
          f"{ip['value']:<40} {winning:<15} {geo_col:<20} {all_str}"
        )
      else:
        print(
          f"  {ip['rel']:<12} {occ_col:<10} "
          f"{ip['value']:<40} {winning:<15} {geo_col}"
        )

  if verbosity < 2:
    return

  print("\n=== Cookies ===")
  for c in cookies:
    flags = []
    if c.get("third_party"):
      flags.append("3rd-party")
    if c.get("cross_site"):
      flags.append("cross-site")
    print(f"  {c['name']:<30} {', '.join(flags)}")

  print("\n=== JSON-LD ===")
  for i, block in enumerate(jsonld, 1):
    print(f"  Block {i}: {block.get('@type', '?')}")

  print("\n=== Microdata ===")
  for i, block in enumerate(microdata, 1):
    print(f"  Block {i}: {block.get('type', '?')}")


def render_output(
  extracted: dict,
  output_mode: str,
  config: dict,
  verbosity: int = 0,
) -> None:
  """Render analysis results to STDOUT in the requested format.

  Args:
    extracted: Dict returned by extract_data().
    output_mode: 'text' | 'json' | 'yaml'
    config: Merged altbrow config — config["provider"] used for label lookup.
    verbosity: Detail level for text mode (0=summary, 1=domains, 2=full).
  """
  if output_mode == "text":
    providers = config.get("provider") or {}
    _render_text(extracted, verbosity, providers)
    return

  if output_mode == "json":
    print(json.dumps(extracted, indent=2, ensure_ascii=False))
    return

  if output_mode == "yaml":
    if yaml is None:
      raise RuntimeError("YAML output requested but PyYAML is not installed")
    print(yaml.safe_dump(extracted, sort_keys=False, allow_unicode=True))
    return

  # fallback: explicit_format from config
  fmt = config.get("output", {}).get("explicit_format", "json")

  if fmt == "json":
    print(json.dumps(extracted, indent=2, ensure_ascii=False))
  elif fmt == "yaml":
    if yaml is None:
      raise RuntimeError("YAML output requested but PyYAML is not installed")
    print(yaml.safe_dump(extracted, sort_keys=False, allow_unicode=True))
  else:
    raise ValueError(f"Unknown output format: {fmt}")


def write_log(extracted: dict, path: str) -> None:
  """Write full analysis result as JSON to a file.

  Args:
    extracted: Dict returned by extract_data().
    path: Output file path.
  """
  with open(path, "w", encoding="utf-8") as f:
    json.dump(extracted, f, indent=2, ensure_ascii=False)