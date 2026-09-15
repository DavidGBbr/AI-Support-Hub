from sqlalchemy.engine.url import make_url

from app.core.config import Settings


def test_sqlalchemy_url_preserves_reserved_password_characters() -> None:
    password = "p@ss:word/x#y%"
    settings = Settings(
        postgres_host="postgres",
        postgres_user="user",
        postgres_password=password,
        postgres_db="db",
        redis_host="redis",
    )
    parsed = make_url(settings.sqlalchemy_url)
    assert parsed.password == password
    assert parsed.username == "user"
    assert parsed.host == "postgres"
    assert parsed.database == "db"
