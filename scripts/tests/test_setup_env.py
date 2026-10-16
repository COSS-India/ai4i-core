"""Tests for scripts/setup-env.sh.

Each test copies the script and every real env.template into a temp tree, so
the repo's own .env files are never touched.

Run: python3 -m pytest scripts/tests
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"node_modules", ".venv", ".git"}


def _templates():
    for path in REPO_ROOT.rglob("env.template"):
        if not SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts):
            yield path


@pytest.fixture
def root(tmp_path):
    for template in _templates():
        dest = tmp_path / template.relative_to(REPO_ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(template, dest)
    (tmp_path / "scripts").mkdir(exist_ok=True)
    shutil.copy(REPO_ROOT / "scripts" / "setup-env.sh", tmp_path / "scripts")
    return tmp_path


def run_setup(root):
    return subprocess.run(
        ["bash", str(root / "scripts" / "setup-env.sh")],
        cwd=root,
        capture_output=True,
        text=True,
    )


def read_env(path):
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def test_platform_name_with_sed_metacharacters_is_copied_verbatim(root):
    name = r"R&D | Labs \ AI"
    (root / ".env").write_text(f"PLATFORM_NAME={name}\n")

    result = run_setup(root)

    assert result.returncode == 0, result.stderr
    for service in (
        "frontend/simple-ui",
        "services/auth-service",
        "services/platform-core-service",
    ):
        assert read_env(root / service / ".env")["PLATFORM_NAME"] == name


def test_postgres_password_with_sed_metacharacters_is_copied_verbatim(root):
    password = r"p&ss|w\rd"
    (root / ".env").write_text(f"POSTGRES_PASSWORD={password}\n")

    result = run_setup(root)

    assert result.returncode == 0, result.stderr
    auth = read_env(root / "services/auth-service/.env")
    assert auth["AUTH_DB_PASSWORD"] == password


PLATFORM_CORE = "services/platform-core-service/.env"
INFERENCE = "services/inference-service/.env"


def test_rerun_keeps_service_credentials_key_and_shared_secret(root):
    (root / ".env").write_text("")
    assert run_setup(root).returncode == 0
    first = read_env(root / PLATFORM_CORE)

    result = run_setup(root)

    assert result.returncode == 0, result.stderr
    again = read_env(root / PLATFORM_CORE)
    for key in ("SERVICE_CREDENTIALS_ENCRYPTION_KEY", "INTERNAL_SERVICE_SHARED_SECRET"):
        assert first[key]
        assert again[key] == first[key]
    assert "new random value" not in result.stdout


def test_rerun_keeps_hand_set_key(root):
    # A key set before setup-env.sh managed it (old manual step) must survive.
    (root / ".env").write_text("")
    assert run_setup(root).returncode == 0
    env = root / PLATFORM_CORE
    stored = "a2V5LXRoYXQtZW5jcnlwdGVkLWV4aXN0aW5nLXJvd3M="
    env.write_text(
        env.read_text().replace(
            f"SERVICE_CREDENTIALS_ENCRYPTION_KEY={read_env(env)['SERVICE_CREDENTIALS_ENCRYPTION_KEY']}",
            f"SERVICE_CREDENTIALS_ENCRYPTION_KEY={stored}",
        )
    )

    assert run_setup(root).returncode == 0

    assert read_env(env)["SERVICE_CREDENTIALS_ENCRYPTION_KEY"] == stored


def test_generated_secrets_are_valid_and_shared_secret_matches(root):
    import base64

    (root / ".env").write_text("")
    assert run_setup(root).returncode == 0

    platform_core = read_env(root / PLATFORM_CORE)
    inference = read_env(root / INFERENCE)
    key = base64.b64decode(platform_core["SERVICE_CREDENTIALS_ENCRYPTION_KEY"], validate=True)
    assert len(key) == 32
    assert platform_core["INTERNAL_SERVICE_SHARED_SECRET"]
    assert inference["MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN"] == platform_core["INTERNAL_SERVICE_SHARED_SECRET"]


def test_inference_token_is_reused_when_platform_core_env_is_missing(root):
    (root / ".env").write_text("")
    assert run_setup(root).returncode == 0
    token = read_env(root / INFERENCE)["MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN"]
    assert token
    (root / PLATFORM_CORE).unlink()

    assert run_setup(root).returncode == 0

    assert read_env(root / PLATFORM_CORE)["INTERNAL_SERVICE_SHARED_SECRET"] == token


def test_root_env_override_wins(root):
    (root / ".env").write_text("")
    assert run_setup(root).returncode == 0
    (root / ".env").write_text("INTERNAL_SERVICE_SHARED_SECRET=pinned-secret\n")

    assert run_setup(root).returncode == 0

    assert read_env(root / PLATFORM_CORE)["INTERNAL_SERVICE_SHARED_SECRET"] == "pinned-secret"
    assert read_env(root / INFERENCE)["MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN"] == "pinned-secret"


def test_pii_key_is_reused_from_platform_core_when_auth_env_is_missing(root):
    (root / ".env").write_text("")
    assert run_setup(root).returncode == 0
    key = read_env(root / "services/auth-service/.env")["PII_ENCRYPTION_KEY"]
    assert key
    (root / "services/auth-service/.env").unlink()

    assert run_setup(root).returncode == 0

    assert read_env(root / "services/auth-service/.env")["PII_ENCRYPTION_KEY"] == key
    assert read_env(root / PLATFORM_CORE)["PII_ENCRYPTION_KEY"] == key
