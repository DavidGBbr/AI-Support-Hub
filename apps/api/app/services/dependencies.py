from dataclasses import dataclass

from sqlalchemy import text

from app.core.db import engine
from app.core.redis import get_redis


@dataclass(frozen=True)
class DependencyReport:
    postgres: bool
    redis: bool

    @property
    def ok(self) -> bool:
        return self.postgres and self.redis


def check_postgres() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


def check_redis() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:
        return False


def probe_dependencies() -> DependencyReport:
    return DependencyReport(postgres=check_postgres(), redis=check_redis())
