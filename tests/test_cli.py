# tests/test_cli.py
import sys
import subprocess

def test_cli_validate():
    result = subprocess.run(
        [sys.executable, "-m", "altbrow", "--validate-config"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
