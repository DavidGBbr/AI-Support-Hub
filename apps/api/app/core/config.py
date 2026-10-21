from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str
    postgres_port: int = 5432
    postgres_user: str
    postgres_password: str
    postgres_db: str
    redis_host: str
    redis_port: int = 6379
    redis_db: int = 0
    celery_result_db: int = 1
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Stripe. Only test mode is supported: the secret key guard below refuses
    # any live key so a misconfigured environment can never charge a customer.
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_pro_price_id: str = ""
    # Legacy alias kept so existing local .env files keep working.
    stripe_price_id: str = ""
    stripe_webhook_secret: str = ""
    web_base_url: str = "http://localhost:3000"

    # Plan limits. The numbers are configuration so the Tech Lead can change
    # them without a code change; the defaults match the task description.
    plan_free_max_knowledge_bases: int = 1
    plan_pro_max_knowledge_bases: int = 5
    # Subscription statuses that keep a workspace on the Pro plan.
    plan_pro_statuses: str = "active,trialing"

    # Development-only seam for the billing endpoints. It stands in for the
    # server-side membership resolution described in ADR 0001 and is replaced
    # when the authentication and workspace cards land. It fails closed: with
    # no token configured the billing endpoints answer 503.
    billing_admin_token: str = ""
    billing_admin_workspace_id: str = ""

    @field_validator("stripe_secret_key")
    @classmethod
    def _reject_live_secret_key(cls, value: str) -> str:
        if value and not value.startswith("sk_test_"):
            raise ValueError(
                "STRIPE_SECRET_KEY must be a Stripe test key (sk_test_...); "
                "this deployment only supports Stripe test mode"
            )
        return value

    @field_validator("stripe_publishable_key")
    @classmethod
    def _reject_live_publishable_key(cls, value: str) -> str:
        if value and not value.startswith("pk_test_"):
            raise ValueError(
                "STRIPE_PUBLISHABLE_KEY must be a Stripe test key (pk_test_...)"
            )
        return value

    @property
    def sqlalchemy_url(self) -> str:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.celery_result_db}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def stripe_pro_price(self) -> str:
        """Stripe price id of the paid plan."""
        return self.stripe_pro_price_id or self.stripe_price_id

    @property
    def plan_pro_status_set(self) -> frozenset[str]:
        return frozenset(
            status.strip()
            for status in self.plan_pro_statuses.split(",")
            if status.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
