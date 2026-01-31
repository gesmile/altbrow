from domain_utils import get_registrable_domain

def classify_domain(domain: str, page_domain: str, config: dict) -> dict:
  domain = domain.lower()
  page_domain = page_domain.lower()

  reg_domain = get_registrable_domain(domain)
  reg_page = get_registrable_domain(page_domain)

  trust = "UNKNOWN"
  trust_cfg = config.get("trust", {})

  if reg_domain in trust_cfg.get("trusted_domains", []):
    trust = "TRUSTED"
  elif reg_domain in trust_cfg.get("insecure_domains", []):
    trust = "INSECURE"

  # First Party: gleiche registrable Domain
  if reg_domain == reg_page:
    return {
      "domain": domain,
      "class": "FIRST_PARTY",
      "registrable_domain": reg_domain,
      "relation": "SUBDOMAIN",
      "trust": trust
    }

  # Klassifikation über Config-Gruppen
  domain_groups = config.get("domains", {})

  for group, entries in domain_groups.items():
    for entry in entries:
      entry = entry.lower()
      entry_reg = get_registrable_domain(entry)
      if reg_domain == entry_reg:
        return {
          "domain": domain,
          "class": group.upper(),
          "registrable_domain": reg_domain,
          "relation": "EXTERNAL",
          "trust": trust
        }

  return {
    "domain": domain,
    "class": "OTHER",
    "registrable_domain": reg_domain,
    "relation": "EXTERNAL",
    "trust": trust
  }
