# tests/conftest.py
#
# Shared pytest fixtures for altbrow integration tests.
# Provides a local HTTP server serving test HTML pages from tests/data/.

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


@pytest.fixture(scope="session")
def mock_server():
  """Start a local HTTP server serving tests/data/ for the test session.

  Returns:
    Base URL string e.g. 'http://127.0.0.1:8080'
  """
  server = HTTPServer((MOCK_HOST, MOCK_PORT), _SilentHandler)
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  yield MOCK_BASE_URL
  server.shutdown()
