import tldextract


def get_registrable_domain(domain: str) -> str:
  ext = tldextract.extract(domain)
  if not ext.domain or not ext.suffix:
    return domain.lower()
  return f"{ext.domain}.{ext.suffix}".lower()
