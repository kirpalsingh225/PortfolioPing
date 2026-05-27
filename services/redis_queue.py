from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from config import get_settings


async def get_redis_pool() -> ArqRedis:
    settings = get_settings()
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))
