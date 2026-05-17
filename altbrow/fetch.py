import logging
import requests
import unicodedata
import urllib3

from urllib.parse import urlparse, quote, unquote

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
  """Normalize a URL for safe HTTP transmission.

  Applies Unicode NFC normalization to the path component, then
  re-encodes it with percent-encoding. Already-encoded sequences
  are decoded first to avoid double-encoding.

  This handles IRI (Internationalized Resource Identifiers) as used
  in Malayalam, Arabic, CJK and other non-ASCII URLs pasted from
  browsers or copy-paste with shell encoding artifacts.

  Args:
    url: Raw URL string, may contain Unicode path or broken percent-encoding.

  Returns:
    URL with NFC-normalized, correctly percent-encoded path.
  """
  parsed = urlparse(url)

  # decode any existing percent-encoding, then NFC-normalize, then re-encode
  path_decoded = unquote(parsed.path, encoding="utf-8", errors="replace")
  path_nfc     = unicodedata.normalize("NFC", path_decoded)
  path_encoded = quote(path_nfc, safe="/:@!$&'()*+,;=")

  return parsed._replace(path=path_encoded).geturl()


def _build_transport(response: "requests.Response", check_cert: bool = True) -> dict:
  """Build transport metadata from an active requests.Response.

  Must be called before response.text is accessed to ensure the
  underlying SSL socket is still reachable for cipher inspection.

  Args:
    response: Active response object (body not yet consumed).
    check_cert: Whether TLS certificate was verified (from client profile).

  Returns:
    Dict with keys:
      http.version    - HTTP version string or None
      http.redirects  - list of {"url", "status"} dicts
      tls             - dict with protocol/cipher/pki, or None for plain HTTP
  """
  raw = response.raw

  version_code = getattr(raw, "version", None)
  http_version = {10: "HTTP/1.0", 11: "HTTP/1.1", 20: "HTTP/2"}.get(version_code)

  redirects = [
    {"url": r.url, "status": r.status_code}
    for r in response.history
  ]

  tls: dict | None = None
  try:
    sock = None
    # urllib3 v1/v2: connection still checked out
    conn = getattr(raw, "_connection", None) or getattr(raw, "connection", None)
    if conn is not None:
      sock = getattr(conn, "sock", None)
    # urllib3 v2: connection released to pool but _sock_shutdown keeps a reference
    if sock is None:
      shutdown_ref = getattr(raw, "_sock_shutdown", None)
      if shutdown_ref is not None:
        sock = getattr(shutdown_ref, "__self__", None)
    if sock is not None and hasattr(sock, "cipher"):
      info = sock.cipher()
      if info:
        tls = {
          "protocol": info[1].replace("TLSv", "TLS "),
          "cipher":   info[0],
          "pki":      "valid" if check_cert else "unknown",
        }
  except Exception as exc:
    logger.debug("_build_transport TLS error: %s", exc)

  return {
    "http": {
      "version":   http_version,
      "headers":   dict(response.headers),
      "redirects": redirects,
    },
    "tls": tls,
  }


def fetch_url(url: str, client_profile: dict) -> dict:
  """Fetch a URL using the given client profile settings.

  The URL is NFC-normalized before the request to handle non-ASCII paths
  (IRI) correctly across shells and operating systems.

  Args:
    url: Target URL (http or https).
    client_profile: Merged client profile dict from config.
      Relevant keys:
        headers (dict)        - HTTP request headers
        use_session (bool)    - use requests.Session for cookies
        check_cert (bool)     - verify TLS certificate (default True)
        timeout (int)         - request timeout in seconds (default 10)

  Returns:
    Dict with keys:
      url          - original URL as given
      final_url    - URL after redirects
      status_code  - HTTP response status
      headers      - response headers dict
      encoding     - response encoding
      html         - response body as string
      cookies      - CookieJar
      transport    - connection layer metadata (HTTP version, redirects, TLS)

  Raises:
    requests.exceptions.MissingSchema: Invalid URL.
    requests.exceptions.Timeout: Request timed out.
    requests.exceptions.ConnectionError: Network unreachable.
    requests.exceptions.HTTPError: 4xx/5xx response.
    requests.exceptions.RequestException: Any other request failure.
  """
  headers     = client_profile.get("headers", {})
  use_session = client_profile.get("use_session", False)
  check_cert  = client_profile.get("check_cert", True)
  timeout     = client_profile.get("timeout", 10)

  if not check_cert:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

  normalized_url = _normalize_url(url)
  if normalized_url != url:
    logger.debug("URL normalized: %s -> %s", url, normalized_url)

  try:
    # Always use an explicit Session so the underlying SSL socket stays
    # accessible after the request (requests.get() closes its internal
    # session before returning, which clears _connection and kills cipher()).
    session = requests.Session()
    if headers:
      session.headers.update(headers)
    response = session.get(normalized_url, timeout=timeout, verify=check_cert)
    cookies  = session.cookies if use_session else response.cookies

    response.raise_for_status()

    logger.debug(
      "Fetched %s (status %s)",
      response.url,
      response.status_code
    )

    transport = _build_transport(response, check_cert)
    html      = response.text

    return {
      "url":         url,           # original as given by user
      "final_url":   response.url,
      "status_code": response.status_code,
      "headers":     dict(response.headers),
      "encoding":    response.encoding,
      "html":        html,
      "cookies":     cookies,
      "transport":   transport,
    }

  except requests.exceptions.MissingSchema:
    logger.error("Invalid URL (missing scheme): %s", url)
    raise

  except requests.exceptions.Timeout:
    logger.error("Timeout while fetching %s", url)
    raise

  except requests.exceptions.ConnectionError as exc:
    exc_str = str(exc)
    if "no.access" in exc_str or "NameResolutionError" in exc_str and "no.access" in exc_str:
      logger.error(
        "Server redirected %s to a block page (no.access) — "
        "site may require browser headers (try --client-profile browser)", url
      )
    elif "NewConnectionError" in exc_str or "Connection refused" in exc_str or "WinError" in exc_str:
      logger.error("Connection refused for %s (host unreachable or port closed)", url)
    elif "SSLError" in exc_str or "SSL" in exc_str:
      logger.error("TLS error for %s (try --no-cert-check for self-signed certs)", url)
    else:
      logger.error("Connection error for %s: %s", url, exc)
    raise

  except requests.exceptions.HTTPError as exc:
    status = exc.response.status_code if exc.response else "?"
    has_non_ascii = any(ord(c) > 127 for c in url)
    is_404 = status == 404 or "404" in str(exc)
    hint = (
      " (non-ASCII URL path: shell may have dropped combining characters)"
      if is_404 and has_non_ascii
      else ""
    )
    logger.error("HTTP error %s for %s%s", status, url, hint)
    raise

  except requests.exceptions.RequestException as exc:
    logger.error("Request failed for %s: %s", url, exc)
    raise
