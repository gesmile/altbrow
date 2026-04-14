# altbrow/classify_cookies.py
#
#   classify_cookies()


def classify_cookies(raw_cookie: str, page_domain: str) -> dict:
  """Parse and classify a raw Set-Cookie header value.

  Determines whether the cookie is third-party and whether it is
  configured for cross-site delivery (SameSite=None).

  Args:
    raw_cookie: Raw Set-Cookie header string (single cookie).
    page_domain: Hostname of the analysed page.

  Returns:
    Dict with keys:
      name        - cookie name
      third_party - True if cookie domain differs from page domain
      cross_site  - True if SameSite=None is set
      attributes  - list of raw attribute strings (e.g. 'HttpOnly', 'Path=/')
  """
  parts = [p.strip() for p in raw_cookie.split(";")]
  name, *_ = parts[0].split("=", 1)

  result = {
    "name":        name,
    "third_party": False,
    "cross_site":  False,
    "attributes":  [],
  }

  for part in parts[1:]:
    lower = part.lower()
    result["attributes"].append(part)

    if lower.startswith("domain="):
      domain = lower.split("=", 1)[1].lstrip(".")
      if domain and domain != page_domain:
        result["third_party"] = True

    if lower == "samesite=none":
      result["cross_site"] = True

  return result
