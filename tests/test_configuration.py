import os
from pathlib import Path
import subprocess
import sys

import pytest


def run_config(code, **variables):
    environment = {key: value for key, value in os.environ.items() if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    environment.update({"PRODUCTION": "0", **variables})
    return subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], env=environment, capture_output=True, text=True)


@pytest.mark.parametrize("secret", ["", " ", "short"])
def test_production_rejects_empty_or_weak_signing_key(secret):
    result = run_config("import app.config", SECRET_KEY=secret, PRODUCTION="1")
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_development_generates_and_persists_a_key(tmp_path):
    secret_file = tmp_path / "local-secret"
    code = (
        "import os\n"
        "from pathlib import Path\n"
        "from unittest.mock import patch\n"
        "key = 'x' * 48\n"
        "with patch('secrets.token_urlsafe', return_value=key):\n"
        "    import app.config\n"
        "assert app.config.settings.SECRET_KEY == key\n"
        "assert Path(os.environ['LOCAL_SECRET_FILE']).read_text().strip() == key\n"
    )
    result = run_config(code, LOCAL_SECRET_FILE=str(secret_file))
    assert result.returncode == 0, result.stderr


def test_development_reuses_the_persisted_key(tmp_path):
    secret_file = tmp_path / "local-secret"
    secret_file.write_text("k" * 48, encoding="utf-8")
    code = "import app.config; assert app.config.settings.SECRET_KEY == 'k' * 48"
    result = run_config(code, LOCAL_SECRET_FILE=str(secret_file))
    assert result.returncode == 0, result.stderr


def test_false_environment_flags_do_not_enable_production():
    result = run_config("import app.config; assert not app.config.settings.IS_PRODUCTION")
    assert result.returncode == 0, result.stderr
