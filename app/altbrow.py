import argparse
import logging
# import pprint

from fetch import fetch_url
from extract import extract_data
from logging_config import setup_logging
from config import load_config, get_client_profile, ConfigError
from output import render_output, write_log


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("url", help="URL to analyze")
  parser.add_argument("--debug", action="store_true", help="Enable debug logging")
  parser.add_argument("--output-mode", choices=["silent", "summary", "explicit"], default="summary", help="Control result visibility")
  parser.add_argument("--log-file", help="Write full analysis result to file (JSON)" )
  parser.add_argument("--client-profile", choices=["passive", "browser", "consented"], help="HTTP client behavior profile (default: from config)")

  args = parser.parse_args()

  setup_logging(debug=args.debug)
  logger = logging.getLogger(__name__)

  try:
    config = load_config()
    client_profile = get_client_profile(config, args.client_profile)
  except ConfigError as exc:
    logging.error("Config error: %s", exc)
    return

  try:
    fetched = fetch_url(args.url, client_profile)
    extracted = extract_data(fetched, config)
  except Exception as exc:
    logger.error("Analysis failed: %s", exc)
    return

  render_output(extracted, args.output_mode)

  if args.log_file:
      write_log(extracted, args.log_file)

if __name__ == "__main__":
  main()
