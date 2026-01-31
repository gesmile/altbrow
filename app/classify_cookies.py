def classify_cookies(raw_cookie: str, page_domain: str, config) -> dict:
  parts = [p.strip() for p in raw_cookie.split(";")]

  name, *_ = parts[0].split("=", 1)

  result = {
    "name": name,
    "third_party": False,
    "cross_site": False,
    "attributes": [],
  }

  for part in parts[1:]:
    lower = part.lower()
    result["attributes"].append(part)

    if lower.startswith("domain="):
      domain = lower.split("=", 1)[1].lstrip(".")
      if domain != page_domain:
        result["third_party"] = True

    if lower == "samesite=none":
      result["cross_site"] = True

  return result

