from pprint import pprint
import json


def render_output(extracted: dict, output_mode: str) -> None:
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
        structured = extracted.get("structured_data", {})
        jsonld = structured.get("json-ld", [])
        microdata = structured.get("microdata", [])

        print("\n=== External Domains ===")
        pprint(extracted["signals"]["external_domains"])

        print("\n=== Cookies ===")
        pprint(extracted["signals"]["cookies"])

        print("\n=== Structured Data: JSON-LD ===")
        if not jsonld:
            print("(none)")
        else:
            for idx, block in enumerate(jsonld, start=1):
                print(f"\n--- JSON-LD Block {idx} ---")
                pprint(block)

        print("\n=== Structured Data: Microdata ===")
        if not microdata:
            print("(none)")
        else:
            for idx, block in enumerate(microdata, start=1):
                print(f"\n--- Microdata Block {idx} ---")
                pprint(block)

def write_log(extracted: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(extracted, f, indent=2, ensure_ascii=False)
