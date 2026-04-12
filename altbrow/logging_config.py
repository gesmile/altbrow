import logging


def setup_logging(debug: bool = False) -> None:
  level = logging.DEBUG if debug else logging.INFO

  logging.basicConfig(
    level=level,
    format="%(levelname)s:%(name)s:%(message)s"
  )
