import os
from pathlib import Path
import subprocess
import sys

import pytest


def run_config(code, **variables):
    environment = {key: value for key, value in os.environ.items() if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    environment.update({"PRODUCTION": "0", "VERCEL": "0", **variables})
    return subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], env=environment, capture_output=True, text=True)


@pytest.mark.parametrize("secret", ["", " ", "short"])
def test_production_rejects_empty_or_weak_signing_key(secret):
    result = run_config("import app.config", SECRET_KEY=secret, PRODUCTION="1")
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_development_generates_a_key_instead_of_using_a_known_default():
    code = "from unittest.mock import patch; key = 'x' * 48\nwith patch('secrets.token_urlsafe', return_value=key):\n import app.config\n assert app.config.settings.SECRET_KEY == key"
    result = run_config(code)
    assert result.returncode == 0, result.stderr


def test_false_environment_flags_do_not_enable_production():
    result = run_config("import app.config; assert not app.config.settings.IS_PRODUCTION")
    assert result.returncode == 0, result.stderr
