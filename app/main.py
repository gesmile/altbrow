import argparse
import logging

from .fetch import fetch_url
from .extract import extract_data
from .logging_config import setup_logging
from .config import load_toml, get_client_profile, ConfigError, validate_altbrow_config
from .output import render_output, write_log


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("url", nargs="?", help="URL to analyze")
  parser.add_argument("--debug", action="store_true", help="Enable debug logging")
  parser.add_argument(
    "--output-mode",
    choices=["silent", "summary", "explicit"],
    default="summary",
    help="Control result visibility",
  )
  parser.add_argument("--log-file", help="Write full analysis result to file (JSON)")
  parser.add_argument(
    "--client-profile",
    choices=["passive", "browser", "consented"],
    help="HTTP client behavior profile (default: from config)",
  )
  parser.add_argument(
    "--validate-config",
    action="store_true",
    help="Validate altbrow.toml and exit"
  )

  args = parser.parse_args()

  setup_logging(debug=args.debug)
  logger = logging.getLogger(__name__)

  try:
    config = load_toml("config/altbrow.toml")
    client_profile = get_client_profile(config, args.client_profile)
  except ConfigError as exc:
    logger.error("Config error: %s", exc)
    return

  if args.validate_config:
    try:
      text = validate_altbrow_config(config)
      print(text)
      return
    except ConfigError as exc:
      logger.error("Config validation failed: %s", exc)
      return

  if not args.url:
    logger.error("URL is required")
    return

  url = args.url
  if not url.startswith(("http://", "https://")):
    url = "https://" + url


  try:
    fetched = fetch_url(url, client_profile)
    extracted = extract_data(fetched, config)
  except Exception as exc:
    logger.error("Analysis failed: %s", exc)
    return

  render_output(extracted, args.output_mode, config)

  if args.log_file:
    write_log(extracted, args.log_file)

if __name__ == "__main__":
  main()
