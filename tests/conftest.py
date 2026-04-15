# tests/conftest.py
#
# Shared pytest fixtures for altbrow integration tests.
# Provides a local HTTP server serving test HTML pages from tests/data/.
#
# In CI: the server is started by the CI step before pytest runs.
#   conftest detects the running server and reuses it.
# Locally: conftest starts its own server for the test session.

import socket
import threading
import pytest

from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

TEST_DATA_DIR = Path(__file__).parent / "data"
MOCK_HOST     = "127.0.0.1"
MOCK_PORT     = 8080
MOCK_BASE_URL = f"http://{MOCK_HOST}:{MOCK_PORT}"


class _SilentHandler(SimpleHTTPRequestHandler):
  """SimpleHTTPRequestHandler with logging suppressed."""

  def __init__(self, *args, **kwargs):
    super().__init__(*args, directory=str(TEST_DATA_DIR), **kwargs)

  def log_message(self, fmt, *args):
    pass  # suppress request logs in test output


def _port_in_use(host: str, port: int) -> bool:
  """Return True if something is already listening on host:port."""
  try:
    with socket.create_connection((host, port), timeout=1):
      return True
  except OSError:
    return False


@pytest.fixture(scope="session")
def mock_server():
  """Provide mock HTTP server URL for the test session.

  If port 8080 is already in use (CI mode), reuses the existing server.
  Otherwise starts a new server (local development mode).

  Returns:
    Base URL string e.g. 'http://127.0.0.1:8080'
  """
  if _port_in_use(MOCK_HOST, MOCK_PORT):
    # CI mode — server already started by CI step
    yield MOCK_BASE_URL
    return

  # Local mode — start our own server
  server = HTTPServer((MOCK_HOST, MOCK_PORT), _SilentHandler)
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  yield MOCK_BASE_URL
  server.shutdown()
  