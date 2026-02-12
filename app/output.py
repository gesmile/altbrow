# from pprint import pprint
import json

try:
  import yaml
except ImportError:
  yaml = None


def render_output(extracted: dict, output_mode: str, config: dict) -> None:
  if output_mode == "silent":
    return

  if output_mode == "summary":
    structured = extracted.get("structured_data", {})
    print("\n=== Summary ===")
    print("External domains:", len(extracted["signals"]["external_domains"]))
    print("Cookies:", len(extracted["signals"]["cookies"]))
    print("JSON-LD blocks:", len(structured.get("json-ld", [])))
    print("Microdata blocks:", len(structured.get("microdata", [])))
    return

  if output_mode == "explicit":
    fmt = config.get("output", {}).get("explicit_format", "json"  )
    
  if fmt == "json": 
    print(json.dumps(extracted, indent=2, ensure_ascii=False))
    return

  if fmt == "yaml":
    if yaml is None:
      raise RuntimeError("YAML output requested but PyYAML is not installed")
    print(
      yaml.safe_dump(
        extracted,
        sort_keys=False,
        allow_unicode=True
      )
    )
    return

  raise ValueError(f"Unknown explicit output format: {fmt}")



def write_log(extracted: dict, path: str) -> None:
  with open(path, "w", encoding="utf-8") as f:
   json.dump(extracted, f, indent=2, ensure_ascii=False)
