from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_COMPOSE_DB_PASSWORD = "postgres"
_WEAK_NEO4J_PASSWORDS = {"development", "neo4j", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: str = "development"

    # Database
    database_url: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    redis_url: str
    redis_password: str | None = None

    # Ollama (embeddings only)
    ollama_url: str
    ollama_embed_model: str

    # Anthropic (LLM) — only required by chat-service; other services leave key unset
    anthropic_api_key: str | None = None
    anthropic_model: str  # required — set by infra (Terraform var.anthropic_model)

    # Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    # CORS
    cors_origins: str

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_production(self, *, require_anthropic: bool = False) -> None:
        """Raise RuntimeError at boot if any insecure defaults are present in production."""
        if self.environment != "production":
            return

        errors: list[str] = []

        if "local-development" in self.jwt_secret_key or len(self.jwt_secret_key) < 32:
            errors.append(
                "JWT_SECRET_KEY is insecure: must be ≥32 chars and not contain 'local-development'"
            )

        if self.neo4j_password in _WEAK_NEO4J_PASSWORDS:
            errors.append(f"NEO4J_PASSWORD is a known weak default: {self.neo4j_password!r}")

        origins = self.cors_origins_list
        if not origins:
            errors.append("CORS_ORIGINS is empty")
        elif "*" in origins or any("localhost" in o for o in origins):
            errors.append("CORS_ORIGINS must not contain '*' or localhost entries in production")

        if f":{_DEFAULT_COMPOSE_DB_PASSWORD}@" in self.database_url:
            errors.append(
                "DATABASE_URL contains the default compose password — set a strong password"
            )

        if not self.ollama_url:
            errors.append(
                "OLLAMA_URL is empty — embed service (CUAI-88) must be deployed before production apply"
            )

        if require_anthropic and not self.anthropic_api_key:
            errors.append(
                "ANTHROPIC_API_KEY must be set when chat-service runs in production"
            )

        if errors:
            raise RuntimeError(
                "Production secret validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )


settings = Settings()
