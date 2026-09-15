from redis import Redis

from app.core.config import get_settings

SOCKET_TIMEOUT_SECONDS = 3


def get_redis() -> Redis:
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
    )
