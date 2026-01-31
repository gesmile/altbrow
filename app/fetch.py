import logging
import requests

logger = logging.getLogger(__name__)


def fetch_url(url: str, client_profile: dict) -> dict:
  headers = client_profile.get("headers", {})
  use_session = client_profile.get("use_session", False)

  try:
    if use_session:
      session = requests.Session()
      if headers:
          session.headers.update(headers)
      response = session.get(url, timeout=10)
      cookies = session.cookies
    else:
      response = requests.get(url, headers=headers or None, timeout=10)
      cookies = response.cookies

    response.raise_for_status()

    logger.debug(
      "Fetched %s (status %s)",
      response.url,
      response.status_code
    )

    return {
      "url": url,
      "final_url": response.url,
      "status_code": response.status_code,
      "headers": dict(response.headers),
      "encoding": response.encoding,
      "html": response.text,
      "cookies": cookies,
    }

  except requests.exceptions.MissingSchema:
    logger.error("Invalid URL (missing scheme): %s", url)
    raise

  except requests.exceptions.Timeout:
    logger.error("Timeout while fetching %s", url)
    raise

  except requests.exceptions.ConnectionError as exc:
    logger.error("Connection error for %s: %s", url, exc)
    raise

  except requests.exceptions.HTTPError as exc:
    logger.error(
      "HTTP error %s for %s",
      exc.response.status_code if exc.response else "?",
      url
    )
    raise

  except requests.exceptions.RequestException as exc:
    logger.error("Request failed for %s: %s", url, exc)
    raise
