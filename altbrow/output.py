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


def _format_categories(cats: list[dict], providers: dict | None = None) -> tuple[str, str]:
  """Split categories into winning (lowest tier) and full sorted list.

  Categories must be pre-sorted by tier ascending (classify_domain does this).
  providers is config["provider"] — used to resolve human-readable provider names.
  category_name is already stored in DB and used directly.

  Returns:
    Tuple (winning, all_str):
      winning - lowest-tier category name, or 'unknown' if no match
      all_str - all as 'category(provider/category_name)', or '-' if no match
  """
  if not cats:
    return "unknown", "-"
  winning = cats[0]["category"]
  providers = providers or {}
  def _fmt(c: dict) -> str:
    p_label = providers.get(c["provider"], {}).get("name") or c["provider"]
    cat_label = c.get("category_name")
    label = f"{p_label}/{cat_label}" if cat_label else p_label
    return c["category"] + "(" + label + ")"
  all_str = ", ".join(_fmt(c) for c in cats)
  return winning, all_str


def _render_text(extracted: dict, verbosity: int, providers: dict | None = None) -> None:
  """Render human-readable text output to STDOUT.

  Args:
    extracted: Dict returned by extract_data().
    verbosity: Detail level (0=summary, 1=domains+ips, 2=full).
    providers: config["provider"] for human-readable label lookup.
    geo_readers: Open GeoReaders for live GeoIP lookup, or None.
  """
  signals    = extracted.get("signals", {})
  structured = extracted.get("structured_data", {})

  domains   = signals.get("external_domains", [])
  ips       = signals.get("external_ips", [])
  cookies   = signals.get("cookies", [])
  jsonld    = structured.get("json-ld", [])
  microdata = structured.get("microdata", [])

  # count by winning category (lowest tier) per domain
  cat_counts: dict[str, int] = {}
  for d in domains:
    cats = d.get("categories", [])
    winning = cats[0]["category"] if cats else "unknown"
    cat_counts[winning] = cat_counts.get(winning, 0) + 1

  cat_summary = ", ".join(
    f"{k}: {v}" for k, v in sorted(cat_counts.items())
  )

  # count by country code from geo field
  geo_counts: dict[str, int] = {}
  for d in domains:
    geo = d.get("geo", "")
    cc = geo.split("/")[0].split(" ")[0] if geo else None
    if cc and len(cc) == 2 and cc.isalpha():
      geo_counts[cc] = geo_counts.get(cc, 0) + 1
  geo_summary = ", ".join(
    f"{k}: {v}" for k, v in sorted(geo_counts.items(), key=lambda x: -x[1])
  )

  # count by winning category (lowest tier) per IP
  ip_cat_counts: dict[str, int] = {}
  for ip in ips:
    cats = ip.get("categories", [])
    winning = cats[0]["category"] if cats else "unknown"
    ip_cat_counts[winning] = ip_cat_counts.get(winning, 0) + 1

  ip_cat_summary = ", ".join(
    f"{k}: {v}" for k, v in sorted(ip_cat_counts.items())
  )

  print("\n=== Summary ===")
  geo_part = f" ({geo_summary})" if geo_summary else ""
  print(f"External domains : {len(domains)}" + (f" ({cat_summary})" if cat_summary else "") + geo_part)
  print(f"External IPs     : {len(ips)}" + (f" ({ip_cat_summary})" if ip_cat_summary else ""))
  print(f"Cookies          : {len(cookies)}")
  print(f"JSON-LD blocks   : {len(jsonld)}")
  print(f"Microdata blocks : {len(microdata)}")

  if verbosity < 1:
    return

  print("\n=== External Domains ===")
  for d in domains:
    winning, all_str = _format_categories(d.get("categories", []), providers)
    geo = d.get("geo", "")
    geo_col = f"[{geo}]" if geo else "-"
    if verbosity >= 2:
      print(
        f"  {d['relation']:<12} {d.get('occurrence',''):<10} "
        f"{d['value']:<40} {winning:<15} {geo_col:<20} {all_str}"
      )
    else:
      print(
        f"  {d['relation']:<12} {d.get('occurrence',''):<10} "
        f"{d['value']:<40} {winning:<15} {geo_col}"
      )

  print("\n=== External IPs ===")
  if not ips:
    print("  (none)")
  else:
    for ip in ips:
      winning, all_str = _format_categories(ip.get("categories", []), providers)
      occurrence = ip.get("occurrence", "")
      geo = ip.get("geo", "")
      geo_col = f"[{geo}]" if geo else "-"
      if verbosity >= 2:
        print(
          f"  {ip['relation']:<12} {occurrence:<10} "
          f"{ip['value']:<40} {winning:<15} {geo_col:<20} {all_str}"
        )
      else:
        print(
          f"  {ip['relation']:<12} {occurrence:<10} "
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
  if not jsonld:
    print("  (none)")
  else:
    for i, block in enumerate(jsonld, 1):
      print(f"  Block {i}: {block.get('@type', '?')}")

  print("\n=== Microdata ===")
  if not microdata:
    print("  (none)")
  else:
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