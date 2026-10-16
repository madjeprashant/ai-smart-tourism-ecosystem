"""STEP 21 - PHASE 1: Production foundation and configuration validation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_config_module_exists():
    source = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    assert "JWT_SECRET_KEY" in source
    assert "CORS_ORIGINS" in source
    assert "validate_runtime_configuration" in source


def test_auth_does_not_embed_the_old_hardcoded_jwt_secret():
    source = (ROOT / "app" / "auth.py").read_text(encoding="utf-8")
    assert "change_this_to_a_long_random_secret_key" not in source
    assert "JWT_SECRET_KEY" in source


def test_production_configuration_rejects_missing_or_weak_secret():
    source = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    assert 'APP_ENV == "production"' in source
    assert "len(supplied_secret) < 32" in source


def test_cors_is_environment_configurable():
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "CORS_ORIGINS" in source
    assert "allow_origins=CORS_ORIGINS" in source


def test_env_example_documents_required_runtime_settings():
    source = (ROOT / ".env.example").read_text(encoding="utf-8")
    for token in ("APP_ENV=", "JWT_SECRET_KEY=", "JWT_EXPIRE_MINUTES=", "CORS_ORIGINS="):
        assert token in source


def test_project_ignores_local_environment_artifacts():
    source = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for token in (".env", "venv/", "__pycache__/", ".pytest_cache/", "*.db"):
        assert token in source
