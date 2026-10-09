from app.core.redis import redis_client


async def invalidate_task_history(user_id) -> int:
    keys = [k async for k in redis_client.scan_iter(match=f"task_history:{user_id}:*")]
    if keys:
        await redis_client.delete(*keys)
    return len(keys)