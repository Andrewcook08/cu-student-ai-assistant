"""Tests for Settings.validate_production() — each failure branch."""

import pytest
from shared.config import Settings


def _prod_settings(**overrides: str) -> Settings:
    """Build a Settings instance with safe production defaults, overridable per test."""
    base = {
        "environment": "production",
        "database_url": "postgresql+psycopg://app:str0ngpassword@db:5432/cu_assistant",
        "neo4j_uri": "bolt://neo4j:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "str0ng-neo4j-password",
        "redis_url": "redis://redis:6379/0",
        "ollama_url": "http://ollama:11434",
        "ollama_embed_model": "nomic-embed-text",
        "anthropic_api_key": "sk-ant-test-key",
        "anthropic_model": "claude-sonnet-4-20250514",
        "jwt_secret_key": "a" * 32,
        "cors_origins": "https://cu-assistant.example.com",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_development_mode_skips_validation() -> None:
    """ENVIRONMENT=development (default) must never raise."""
    s = _prod_settings(environment="development", jwt_secret_key="local-development-secret")
    s.validate_production()  # must not raise


def test_valid_production_config_passes() -> None:
    """A properly configured production instance passes without error."""
    _prod_settings().validate_production()


def test_jwt_contains_local_development() -> None:
    s = _prod_settings(jwt_secret_key="local-development-secret-key-padding")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        s.validate_production()


def test_jwt_too_short() -> None:
    s = _prod_settings(jwt_secret_key="short")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        s.validate_production()


def test_neo4j_password_development() -> None:
    s = _prod_settings(neo4j_password="development")
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
        s.validate_production()


def test_neo4j_password_neo4j() -> None:
    s = _prod_settings(neo4j_password="neo4j")
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
        s.validate_production()


def test_neo4j_password_empty() -> None:
    s = _prod_settings(neo4j_password="")
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
        s.validate_production()


def test_cors_empty() -> None:
    s = _prod_settings(cors_origins="")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        s.validate_production()


def test_cors_wildcard() -> None:
    s = _prod_settings(cors_origins="*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        s.validate_production()


def test_cors_localhost() -> None:
    s = _prod_settings(cors_origins="http://localhost:5173")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        s.validate_production()


def test_database_url_default_compose_password() -> None:
    s = _prod_settings(
        database_url="postgresql+psycopg://postgres:postgres@postgres:5432/cu_assistant"
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        s.validate_production()


def test_multiple_errors_reported_together() -> None:
    """All failures should be reported in a single RuntimeError, not just the first."""
    s = _prod_settings(
        jwt_secret_key="local-development-secret-key-padding",
        neo4j_password="neo4j",
    )
    with pytest.raises(RuntimeError) as exc_info:
        s.validate_production()
    msg = str(exc_info.value)
    assert "JWT_SECRET_KEY" in msg
    assert "NEO4J_PASSWORD" in msg
