import argparse
import logging
import sys

from urllib.parse import urlparse

from altbrow import __version__
from .fetch import fetch_url
from .extract import extract_data
from .logging_config import setup_logging
from .config import (
  load_toml,
  get_client_profile,
  validate_altbrow_config,
  discover_config_path,
  load_provider_config,
  ConfigError,
)
from .cache import build_cache, get_or_build_cache
from .output import render_output, write_log


def main() -> int:
  """Entry point for the altbrow CLI.

  Parses arguments, loads config, builds/validates cache,
  fetches the target URL and renders the analysis output.

  Returns:
    Exit code:
      0 - success
      2 - CLI usage error
      3 - config/cache error
      4 - network/analysis error
  """
  parser = argparse.ArgumentParser()

  parser.add_argument("url", nargs="?", help="URL to analyze")

  parser.add_argument(
    "-V", "--version",
    action="version",
    version=f"Altbrow v{__version__}"
  )

  parser.add_argument(
    "--config",
    help="Path to configuration file (TOML)"
  )

  parser.add_argument(
    "-o", "--output",
    help="Write result to file"
  )

  parser.add_argument(
    "-f", "--format",
    choices=["text", "yaml", "json"],
    default="text",
    help="Output format (default: text)"
  )

  parser.add_argument(
    "-v", "--verbose",
    action="count",
    default=0,
    help="Increase text detail level (-vv, -vvv)"
  )

  parser.add_argument(
    "--client-profile",
    choices=["passive", "browser", "consented"],
    help="HTTP client behavior profile (default: from config)",
  )

  parser.add_argument(
    "--no-cert-check",
    dest="check_cert",
    action="store_false",
    help="Disable TLS certificate verification (self-signed certs, local hosts)"
  )

  parser.add_argument(
    "--validate-config",
    action="store_true",
    help="Validate altbrow.toml and exit"
  )

  parser.add_argument(
    "--build-cache",
    action="store_true",
    help="(Re)build provider cache DB and exit"
  )

  args = parser.parse_args()

  setup_logging(debug=False)
  logger = logging.getLogger("altbrow")

  try:
    config_path = discover_config_path(args.config)
    config = load_toml(config_path)
    client_profile = get_client_profile(config, args.client_profile)
    provider_config = load_provider_config(config_path, config)
  except ConfigError as exc:
    logger.error("Config error: %s", exc)
    return 3

  # --no-cert-check overrides check_cert from profile
  if not args.check_cert:
    client_profile["check_cert"] = False

  if args.validate_config:
    try:
      text = validate_altbrow_config(config, provider_config)
      print(text)
      return 0
    except ConfigError as exc:
      logger.error("Config validation failed: %s", exc)
      return 3

  # --- cache ---
  cache_path = config_path.parent / ".altbrow.cache"

  if args.build_cache:
    if provider_config is None:
      logger.error("--build-cache requires provider config (meta.use-provider = true)")
      return 3
    build_cache(cache_path, provider_config, config_path)
    print(f"Cache built: {cache_path}")
    return 0

  try:
    get_or_build_cache(cache_path, provider_config, config_path)
  except Exception as exc:
    logger.error("Cache build failed: %s", exc)
    return 3

  if not args.url:
    parser.print_usage()
    logger.error("URL is required (or use --validate-config / --build-cache)")
    return 2

  url = args.url
  if not url.startswith(("http://", "https://")):
    url = "https://" + url

  parsed = urlparse(url)

  if parsed.scheme not in ("http", "https") or not parsed.netloc:
    logger.error("Invalid URL")
    return 2

  try:
    fetched = fetch_url(url, client_profile)
    extracted = extract_data(fetched, cache_path)
  except Exception as exc:
    logger.error("Analysis failed: %s", exc)
    return 4

  render_output(extracted, args.format, config, verbosity=args.verbose)

  if args.output:
    write_log(extracted, args.output)

  return 0


if __name__ == "__main__":
  sys.exit(main())
  