from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"

    # CORS — comma-separated list of allowed origins.
    # Use "*" for development; set explicit origins in production.
    cors_origins: str = "*"

    # Database
    database_url: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    task_queue_name: str = "tasks:queue:default"
    task_status_ttl_seconds: int = Field(default=86400, ge=60)
    metrics_active_users_window_min: int = Field(default=15, ge=1, le=1440)

    # JWT
    jwt_secret: str = ""
    jwt_alg: str = "HS256"
    access_token_expire_min: int = 30
    refresh_token_expire_days: int = 7

    # Password hashing
    bcrypt_rounds: int = Field(default=12, ge=4, le=31)

    # Auth rate limit
    login_rate_limit_max_attempts: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_min: int = Field(default=15, ge=1, le=1440)

    # General API rate limit (fixed window per user/IP)
    rate_limit_enabled: bool = True
    rate_limit_max_requests: int = Field(default=120, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    # Storage (MinIO / S3)
    storage_backend: str = "local"
    local_storage_root: str = "./data/storage"
    storage_url_expires_default: int = Field(default=3600, ge=1)
    storage_max_upload_size_bytes: int = Field(default=1073741824, ge=1)
    project_export_async_threshold_entities: int = Field(default=1000, ge=1)

    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "pipeline-production-hub"
    s3_region: str = "us-east-1"

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("JWT_SECRET must be set and non-empty")
        return cleaned

    @field_validator("jwt_alg")
    @classmethod
    def validate_jwt_alg(cls, value: str) -> str:
        cleaned = value.strip()
        supported = {
            "HS256",
            "HS384",
            "HS512",
            "RS256",
            "RS384",
            "RS512",
            "ES256",
            "ES384",
            "ES512",
            "PS256",
            "PS384",
            "PS512",
        }
        if cleaned not in supported:
            raise ValueError(
                "Invalid JWT_ALG value. Check .env formatting and use a supported algorithm "
                "(e.g. HS256)."
            )
        return cleaned


settings = Settings()
